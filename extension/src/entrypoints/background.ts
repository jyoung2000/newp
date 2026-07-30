// Background service worker: the extension executor's driver.
//
// - Holds a WebSocket to /ws/ext (device-token auth) with auto-reconnect and
//   an MV3 service-worker keepalive alarm. Firefox uses a persistent script.
// - Polls /api/ext/next-job when a run is active, opens the apply page in a
//   tab, and hands the job to the content script.
// - Relays content-script results back to the server through the state
//   machine (needs_human, challenge, submit-result).
// - The throughput ceilings and all state transitions are enforced
//   server-side; this driver cannot bypass them.
import browser from "webextension-polyfill";
import * as api from "../lib/api";
import type { ContentToBackground, NextJob } from "../lib/types";
import { TabRelay } from "../lib/relay";

const KEEPALIVE_ALARM = "jobpilot-keepalive";
const POLL_ALARM = "jobpilot-poll";

let ws: WebSocket | null = null;
let wsBackoff = 1000;
let polling = false;
const jobTabs = new Map<number, number>(); // applicationId -> tabId
const tabJobs = new Map<number, NextJob>(); // tabId -> job
let activeRelay: TabRelay | null = null;

export default defineBackground(() => {
  browser.runtime.onInstalled.addListener(() => {
    void setupAlarms();
  });
  browser.runtime.onStartup.addListener(() => {
    void setupAlarms();
    void connectWs();
  });

  browser.alarms.onAlarm.addListener((alarm) => {
    if (alarm.name === KEEPALIVE_ALARM) {
      // Touch storage to keep the SW alive and verify pairing.
      void api.getState();
      if (!ws || ws.readyState > WebSocket.OPEN) void connectWs();
    } else if (alarm.name === POLL_ALARM) {
      void pollLoop();
    }
  });

  browser.runtime.onMessage.addListener((raw: unknown, sender: browser.Runtime.MessageSender): Promise<unknown> => {
    const msg = raw as ContentToBackground | { type: "capture" } | CropRequest;
    if (msg.type === "capture") {
      return captureVisibleTab(sender.tab?.windowId).then((dataUrl) => ({ dataUrl }));
    }
    if (msg.type === "capture.crop") {
      return cropVisibleTab(msg as CropRequest, sender.tab?.windowId);
    }
    return handleContentMessage(msg as ContentToBackground).then(() => ({ ok: true }));
  });

  // Keyboard shortcut: fill the form in the active tab without opening the
  // popup. The content script does the work; this only forwards the trigger.
  browser.commands?.onCommand.addListener((command: string) => {
    if (command !== "autofill-form") return;
    void (async () => {
      const [tab] = await browser.tabs.query({ active: true, currentWindow: true });
      if (tab?.id == null) return;
      try {
        await browser.tabs.sendMessage(tab.id, { type: "bg.autofillNow" });
      } catch {
        // No content script in this tab — a browser page, or a tab that
        // predates the extension being installed or reloaded.
      }
    })();
  });

  void setupAlarms();
  void connectWs();
  void pollLoop();
});

async function setupAlarms(): Promise<void> {
  await browser.alarms.create(KEEPALIVE_ALARM, { periodInMinutes: 0.4 });
  await browser.alarms.create(POLL_ALARM, { periodInMinutes: 0.25 });
}

interface CropRequest {
  type: "capture.crop";
  rect: { x: number; y: number; width: number; height: number };
  dpr: number;
}

/**
 * Crop the visible tab to one field's neighbourhood, for the last-resort label
 * read. Content scripts can't call captureVisibleTab, and sending a whole
 * screenshot to the server to read one label would be both slow and far more
 * of the page than the job needs — so the crop happens here, and only the crop
 * travels.
 */
async function cropVisibleTab(
  req: CropRequest,
  windowId?: number,
): Promise<{ imageB64?: string }> {
  const dataUrl = await captureVisibleTab(windowId);
  if (!dataUrl) return {};
  try {
    const dpr = req.dpr > 0 ? req.dpr : 1;
    const blob = await (await fetch(dataUrl)).blob();
    const bitmap = await createImageBitmap(blob);
    // The screenshot is in device pixels; the rect came from CSS pixels.
    const sx = Math.max(0, Math.round(req.rect.x * dpr));
    const sy = Math.max(0, Math.round(req.rect.y * dpr));
    const sw = Math.min(bitmap.width - sx, Math.round(req.rect.width * dpr));
    const sh = Math.min(bitmap.height - sy, Math.round(req.rect.height * dpr));
    if (sw <= 0 || sh <= 0) return {};
    const canvas = new OffscreenCanvas(sw, sh);
    const ctx = canvas.getContext("2d");
    if (!ctx) return {};
    ctx.drawImage(bitmap, sx, sy, sw, sh, 0, 0, sw, sh);
    const cropped = await canvas.convertToBlob({ type: "image/png" });
    const buf = new Uint8Array(await cropped.arrayBuffer());
    let binary = "";
    for (const byte of buf) binary += String.fromCharCode(byte);
    return { imageB64: btoa(binary) };
  } catch {
    return {};
  }
}

async function captureVisibleTab(windowId?: number): Promise<string | undefined> {
  try {
    return await browser.tabs.captureVisibleTab(windowId ?? browser.windows.WINDOW_ID_CURRENT, {
      format: "png",
    });
  } catch {
    return undefined;
  }
}

// --- WebSocket ------------------------------------------------------------

async function connectWs(): Promise<void> {
  const state = await api.getState();
  if (!state.token || !state.paired) return;
  if (ws && ws.readyState <= WebSocket.OPEN) return;
  const wsUrl =
    state.serverUrl.replace(/^http/, "ws") + `/ws/ext?token=${encodeURIComponent(state.token)}`;
  try {
    ws = new WebSocket(wsUrl);
  } catch {
    scheduleReconnect();
    return;
  }
  ws.onopen = () => {
    wsBackoff = 1000;
    setLinkStatus(true);
  };
  ws.onmessage = (ev) => handleWsMessage(ev.data);
  ws.onclose = () => {
    setLinkStatus(false);
    scheduleReconnect();
  };
  ws.onerror = () => ws?.close();
}

function scheduleReconnect(): void {
  wsBackoff = Math.min(wsBackoff * 2, 30000);
  setTimeout(() => void connectWs(), wsBackoff);
}

async function handleWsMessage(data: string): Promise<void> {
  let msg: Record<string, unknown>;
  try {
    msg = JSON.parse(data);
  } catch {
    return;
  }
  const type = msg.type as string;
  if (type === "badge") {
    await updateBadge(Number(msg.open_interventions || 0));
  } else if (type === "intervention.answered") {
    // A human answered — nudge the relevant tab to resume.
    const appId = Number(msg.application_id);
    const tabId = jobTabs.get(appId);
    const job = tabId ? tabJobs.get(tabId) : undefined;
    if (tabId && job) {
      await browser.tabs.sendMessage(tabId, { type: "bg.interventionsAnswered", applicationId: appId }).catch(() => {});
    }
  } else if (type === "notification") {
    await notify(String(msg.title || "JobPilot"), String(msg.message || ""));
  } else if (type === "run.stopped") {
    for (const tabId of tabJobs.keys()) {
      await browser.tabs.sendMessage(tabId, { type: "bg.stop" }).catch(() => {});
    }
  } else if (type === "relay.input") {
    // A real human input event forwarded from the container UI.
    if (activeRelay && msg.event) {
      await activeRelay.forwardInput({
        kind: msg.kind === "key" ? "key" : "mouse",
        event: msg.event as Record<string, unknown>,
      });
    }
  }
}

function setLinkStatus(online: boolean): void {
  void browser.storage.local.set({ wsOnline: online });
}

// --- Polling & job driving ------------------------------------------------

async function pollLoop(): Promise<void> {
  if (polling) return;
  polling = true;
  try {
    const state = await api.getState();
    if (!state.paired || !state.token) return;
    // Only claim one job at a time (the tab drives it to completion).
    if (tabJobs.size > 0) return;
    const resp = await api.nextJob();
    if (resp.job) {
      await startJob(resp.job);
    }
  } catch {
    /* server unreachable; the alarm retries */
  } finally {
    polling = false;
  }
}

async function startJob(job: NextJob): Promise<void> {
  const url = job.listing.apply_url || job.listing.canonical_url;
  const tab = await browser.tabs.create({ url, active: false });
  if (tab.id == null) return;
  jobTabs.set(job.application_id, tab.id);
  tabJobs.set(tab.id, job);

  // Wait for the tab to finish loading, then hand it the job.
  const onUpdated = (tabId: number, info: browser.Tabs.OnUpdatedChangeInfoType) => {
    if (tabId === tab.id && info.status === "complete") {
      browser.tabs.onUpdated.removeListener(onUpdated);
      browser.tabs.sendMessage(tab.id, { type: "bg.fillJob", job }).catch(() => {});
    }
  };
  browser.tabs.onUpdated.addListener(onUpdated);
}

async function handleContentMessage(msg: ContentToBackground): Promise<void> {
  switch (msg.type) {
    case "content.ready":
      return;
    case "content.needsHuman":
      await api.createInterventions(msg.applicationId, msg.items, msg.reason).catch(() => {});
      await refreshBadge();
      return;
    case "content.challenge":
      await api
        .createInterventions(
          msg.applicationId,
          [
            {
              kind: "challenge",
              question: "A human-verification challenge appeared. Please solve it in the page.",
              field_meta: { detail: msg.detail, kind: msg.kind },
              screenshot_b64: msg.screenshot,
            },
          ],
          "challenge",
        )
        .catch(() => {});
      await notify(
        "JobPilot paused — a human check appeared",
        "Open the tab and solve it yourself; JobPilot will not touch it.",
      );
      await refreshBadge();
      return;
    case "content.status":
      await api.setStatus(msg.applicationId, msg.status, msg.reason, msg.error).catch(() => {});
      await finishTab(msg.applicationId);
      return;
    case "content.submitted":
      await api
        .submitResult(msg.applicationId, msg.confirmed, msg.snapshot, msg.screenshot)
        .catch(() => {});
      await notify("Application submitted", msg.confirmed ? "Confirmed." : "Submitted (unconfirmed).");
      await finishTab(msg.applicationId);
      return;
  }
}

async function finishTab(applicationId: number): Promise<void> {
  const tabId = jobTabs.get(applicationId);
  if (tabId != null) {
    tabJobs.delete(tabId);
    jobTabs.delete(applicationId);
    // Leave the tab open for the user to see the confirmation; close only
    // background-created draft tabs after a delay is left to the user.
  }
  void pollLoop();
}

// --- Badge & notifications ------------------------------------------------

async function refreshBadge(): Promise<void> {
  try {
    // The server pushes badge counts over WS; this is a fallback via ping.
    await api.ping();
  } catch {
    /* ignore */
  }
}

async function updateBadge(count: number): Promise<void> {
  const action = browser.action ?? browser.browserAction;
  if (!action) return;
  await action.setBadgeText({ text: count > 0 ? String(count) : "" });
  if (action.setBadgeBackgroundColor) {
    await action.setBadgeBackgroundColor({ color: "#f59e0b" });
  }
}

async function notify(title: string, message: string): Promise<void> {
  try {
    await browser.notifications.create({
      type: "basic",
      iconUrl: browser.runtime.getURL("icon/128.png"),
      title,
      message,
    });
  } catch {
    /* notifications may be unavailable */
  }
}
