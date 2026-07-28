import browser from "webextension-polyfill";
import * as api from "../../lib/api";
import { hasDebuggerPermission, requestDebuggerPermission, TabRelay } from "../../lib/relay";
import type { StoredState } from "../../lib/types";

const app = document.getElementById("app")!;

function getBrowserName(): string {
  const ua = navigator.userAgent;
  if (ua.includes("Firefox")) return "firefox";
  if (ua.includes("Edg")) return "edge";
  return "chrome";
}

async function render(): Promise<void> {
  const state = await api.getState();
  const online = ((await browser.storage.local.get({ wsOnline: false })) as { wsOnline: boolean })
    .wsOnline;
  app.innerHTML = "";
  header(online && state.paired);
  if (!state.paired) {
    renderPairing(state);
  } else {
    await renderPaired(state, online);
  }
}

function header(online: boolean): void {
  const head = document.createElement("div");
  head.className = "head";
  head.innerHTML = `
    <span class="dot ${online ? "online" : "offline"}"></span>
    <span class="logo">JobPilot</span>
    <span class="status-pill">${online ? "Linked" : "Not linked"}</span>`;
  app.appendChild(head);
}

function renderPairing(state: StoredState): void {
  const card = document.createElement("div");
  card.className = "card";
  card.innerHTML = `
    <label>JobPilot server URL</label>
    <input type="url" id="server" value="${state.serverUrl}" placeholder="http://localhost:1456" />
    <label>Pairing code (Settings → Extension in JobPilot)</label>
    <input type="text" id="code" class="code-input" maxlength="6" inputmode="numeric" placeholder="000000" />
    <label>Device name</label>
    <input type="text" id="name" value="${defaultDeviceName()}" />
    <div class="error" id="err" style="display:none"></div>
    <button class="btn-primary" id="pair">Pair this browser</button>
    <div class="note">
      JobPilot fills forms in <b>this</b> browser, using your own logged-in
      sessions and your own answers. A human always solves any CAPTCHA.
    </div>`;
  app.appendChild(card);
  card.querySelector<HTMLButtonElement>("#pair")!.addEventListener("click", () => void doPair());
}

function defaultDeviceName(): string {
  const b = getBrowserName();
  const os = navigator.platform || "computer";
  return `${b[0].toUpperCase()}${b.slice(1)} on ${os}`;
}

async function doPair(): Promise<void> {
  const server = (document.getElementById("server") as HTMLInputElement).value.trim().replace(/\/$/, "");
  const code = (document.getElementById("code") as HTMLInputElement).value.trim();
  const name = (document.getElementById("name") as HTMLInputElement).value.trim() || defaultDeviceName();
  const err = document.getElementById("err")!;
  err.style.display = "none";
  if (code.length !== 6) {
    err.textContent = "Enter the 6-digit code from JobPilot.";
    err.style.display = "block";
    return;
  }
  try {
    const result = await api.pair(server, code, name, getBrowserName());
    await api.setState({
      serverUrl: server,
      token: result.token,
      deviceId: result.device_id,
      userEmail: result.user_email,
      paired: true,
    });
    await browser.runtime.sendMessage({ type: "paired" }).catch(() => {});
    await render();
  } catch (e) {
    err.textContent = e instanceof Error ? e.message : "Pairing failed";
    err.style.display = "block";
  }
}

async function renderPaired(state: StoredState, online: boolean): Promise<void> {
  let serverVersion = "";
  let latest: string | null = null;
  try {
    const p = await api.ping();
    serverVersion = p.server_version;
    latest = p.latest_extension_version;
  } catch {
    /* offline */
  }
  const currentVersion = browser.runtime.getManifest().version;
  const updateAvailable = latest && latest !== currentVersion;

  const card = document.createElement("div");
  card.className = "card";
  card.innerHTML = `
    <div class="row"><span class="muted">Account</span><b>${state.userEmail || ""}</b></div>
    <div class="row"><span class="muted">Link</span><span class="${online ? "ok" : "error"}">${online ? "Connected" : "Reconnecting…"}</span></div>
    <div class="row"><span class="muted">Extension</span><span>v${currentVersion}</span></div>
    ${serverVersion ? `<div class="row"><span class="muted">Server</span><span>v${serverVersion}</span></div>` : ""}
    ${updateAvailable ? `<div class="note">A newer extension build (v${latest}) is available from JobPilot → Settings → Extension.</div>` : ""}
  `;
  app.appendChild(card);

  // Humanize override
  const humanizeCard = document.createElement("div");
  humanizeCard.className = "card";
  const humanizeOn = state.humanizeOverride !== false;
  humanizeCard.innerHTML = `
    <div class="row">
      <div>
        <div><b>Type like a human</b></div>
        <div class="muted small">Human-paced entry with the full native event chain. Not cloaking.</div>
      </div>
      <label class="switch">
        <input type="checkbox" id="humanize" ${humanizeOn ? "checked" : ""} />
        <span class="slider"></span>
      </label>
    </div>`;
  app.appendChild(humanizeCard);
  humanizeCard.querySelector<HTMLInputElement>("#humanize")!.addEventListener("change", (e) => {
    void api.setState({ humanizeOverride: (e.target as HTMLInputElement).checked });
  });

  // Remote-hand relay opt-in (Chrome only)
  if (TabRelay.available()) {
    const relayCard = document.createElement("div");
    relayCard.className = "card";
    const granted = await hasDebuggerPermission();
    relayCard.innerHTML = `
      <div><b>Remote CAPTCHA solving</b> ${granted ? '<span class="ok small">enabled</span>' : ""}</div>
      <div class="note">
        Optional. If you're away from this computer and a CAPTCHA appears, you can
        finish it from the JobPilot web app on your phone — <b>your</b> real taps and
        keystrokes drive the real page. JobPilot never solves it for you.
        This needs the browser's <b>debugger</b> permission for the one tab being
        relayed. Nothing is enabled until you grant it.
      </div>
      ${granted ? "" : '<button class="btn-ghost" id="grant" style="margin-top:8px">Enable remote solving…</button>'}`;
    app.appendChild(relayCard);
    const grant = relayCard.querySelector<HTMLButtonElement>("#grant");
    grant?.addEventListener("click", async () => {
      const ok = await requestDebuggerPermission();
      await api.setState({ debuggerRelayOptIn: ok });
      await render();
    });
  } else {
    const fw = document.createElement("div");
    fw.className = "note";
    fw.textContent =
      "On this browser, remote CAPTCHA relay isn't available. If a challenge appears while you're away, the job parks and waits for you to finish it here.";
    app.appendChild(fw);
  }

  const divider = document.createElement("div");
  divider.className = "divider";
  app.appendChild(divider);

  const actions = document.createElement("button");
  actions.className = "btn-ghost";
  actions.textContent = "Open JobPilot";
  actions.addEventListener("click", () => {
    void browser.tabs.create({ url: state.serverUrl });
  });
  app.appendChild(actions);

  const unpair = document.createElement("button");
  unpair.className = "btn-ghost";
  unpair.style.marginTop = "8px";
  unpair.textContent = "Unpair this browser";
  unpair.addEventListener("click", async () => {
    await api.setState({ paired: false, token: null, deviceId: null, userEmail: null });
    await render();
  });
  app.appendChild(unpair);
}

void render();
