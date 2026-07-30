import browser from "webextension-polyfill";
import * as api from "../../lib/api";
import type { CapturedJob } from "../../lib/capture";
import { hasDebuggerPermission, requestDebuggerPermission, TabRelay } from "../../lib/relay";
import { parseLinkCode, resolvePasted } from "../../lib/linkcode";
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
  // One field. The link code carries the server URL with it, so there is
  // nothing to work out and nothing to retype — copy it from JobPilot →
  // Settings → Extension, paste it here.
  const card = document.createElement("div");
  card.className = "card";
  card.innerHTML = `
    <label for="link">Paste your link code</label>
    <textarea id="link" class="link-input" rows="3"
      placeholder="JP1-…"
      autocomplete="off" spellcheck="false"></textarea>
    <div class="muted small">
      In JobPilot: <b>Settings → Extension → Copy link code</b>.
    </div>
    <div class="error" id="err" style="display:none"></div>
    <button class="btn-primary" id="pair" style="margin-top:8px">Link this browser</button>
    <details style="margin-top:10px">
      <summary class="muted small">Enter it manually instead</summary>
      <label for="server" style="margin-top:8px">JobPilot server URL</label>
      <input type="url" id="server" value="${state.serverUrl}" placeholder="http://192.168.1.10:1456" />
      <label for="code">6-digit pairing code</label>
      <input type="text" id="code" class="code-input" maxlength="6" inputmode="numeric" placeholder="000000" />
    </details>
    <div class="note">
      JobPilot fills forms in <b>this</b> browser, using your own logged-in
      sessions and your own answers. A human always solves any CAPTCHA.
    </div>`;
  app.appendChild(card);
  card.querySelector<HTMLButtonElement>("#pair")!.addEventListener("click", () => void doPair());
  const link = card.querySelector<HTMLTextAreaElement>("#link")!;
  link.focus();
  // Pasting is the whole interaction; don't also make them find the button.
  link.addEventListener("paste", () => {
    setTimeout(() => {
      if (parseLinkCode(link.value)) void doPair();
    }, 0);
  });
}

function defaultDeviceName(): string {
  const b = getBrowserName();
  const os = navigator.platform || "computer";
  return `${b[0].toUpperCase()}${b.slice(1)} on ${os}`;
}

async function doPair(): Promise<void> {
  const err = document.getElementById("err")!;
  err.style.display = "none";
  const fail = (message: string): void => {
    err.textContent = message;
    err.style.display = "block";
  };

  const pasted = (document.getElementById("link") as HTMLTextAreaElement).value;
  const manualServer = (document.getElementById("server") as HTMLInputElement).value
    .trim()
    .replace(/\/$/, "");
  const manualCode = (document.getElementById("code") as HTMLInputElement).value.trim();

  // The pasted link code wins; the manual fields are the fallback for someone
  // reading a code off a phone screen.
  let target = pasted.trim() ? resolvePasted(pasted, manualServer) : null;
  if (!target && /^\d{6}$/.test(manualCode) && manualServer) {
    target = { serverUrl: manualServer, code: manualCode };
  }
  if (!target) {
    fail(
      pasted.trim()
        ? "That doesn't look like a link code. Copy it again from JobPilot → Settings → Extension."
        : "Paste your link code, or open “Enter it manually instead”.",
    );
    return;
  }

  // The device names itself; one less box to fill in for no information gained.
  const name = defaultDeviceName();
  try {
    const result = await api.pair(target.serverUrl, target.code, name, getBrowserName());
    const server = target.serverUrl;
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

// --- Save this job --------------------------------------------------------
// The user is looking at a job page and wants it in JobPilot. The active tab
// describes itself (read-only); the popup previews that and posts it on a
// click. Nothing is captured in the background and no site is fetched.

async function askActiveTabForJob(): Promise<CapturedJob> {
  const [tab] = await browser.tabs.query({ active: true, currentWindow: true });
  if (tab?.id == null) throw new Error("no tab");
  const reply = (await browser.tabs.sendMessage(tab.id, { type: "bg.captureJob" })) as
    | { job?: CapturedJob }
    | undefined;
  if (!reply?.job) throw new Error("no reply");
  return reply.job;
}

function renderCapture(state: StoredState): void {
  const card = document.createElement("div");
  card.className = "card";
  card.innerHTML = `
    <div class="capture-head"><b>Save this job</b></div>
    <div class="muted">Reading this page…</div>`;
  app.appendChild(card);

  void (async () => {
    let job: CapturedJob;
    try {
      job = await askActiveTabForJob();
    } catch {
      // Two ordinary causes, and no way to tell them apart from here: the tab
      // predates this extension being installed or reloaded (so nothing is
      // listening in it), or it is a page extensions may not touch at all.
      card.innerHTML = `
        <div class="capture-head"><b>Save this job</b></div>
        <div class="note">
          JobPilot can't read this tab. Reload the job page and reopen this popup —
          tabs opened before the extension was installed or updated aren't
          connected yet. Browser pages (like <b>chrome://</b> or the add-ons store)
          are off-limits to extensions entirely.
        </div>`;
      return;
    }
    card.innerHTML = `
      <div class="capture-head"><b>Save this job</b></div>
      <div class="row"><span class="muted">Title</span><span class="capture-value" id="cap-title"></span></div>
      <div class="row"><span class="muted">Company</span><span class="capture-value" id="cap-company"></span></div>
      ${
        job.confidence === "low"
          ? `<div class="note">We couldn't detect much on this page — it will be saved with what we found.</div>`
          : ""
      }
      <div class="error" id="cap-err" style="display:none"></div>
      <button class="btn-primary" id="cap-save" style="margin-top:8px">Save to JobPilot</button>`;
    // Page-supplied text goes in as text, never as markup.
    card.querySelector("#cap-title")!.textContent = job.title;
    card.querySelector("#cap-company")!.textContent = job.company;

    const save = card.querySelector<HTMLButtonElement>("#cap-save")!;
    save.addEventListener("click", () => void doCapture(card, save, job, state));
  })();
}

async function doCapture(
  card: HTMLElement,
  save: HTMLButtonElement,
  job: CapturedJob,
  state: StoredState,
): Promise<void> {
  const err = card.querySelector<HTMLElement>("#cap-err")!;
  err.style.display = "none";
  save.disabled = true;
  save.textContent = "Saving…";
  try {
    const result = await api.captureJob({
      url: job.url,
      title: job.title,
      company: job.company,
      location: job.location,
      description: job.description,
      salary_raw: job.salary_raw,
      apply_url: job.apply_url,
      posted_at_text: job.posted_at_text,
      source_site: new URL(job.url).hostname,
    });
    save.remove();
    const done = document.createElement("div");
    done.className = "ok";
    done.textContent = result.already_saved ? "Already in your list" : "Saved";
    card.appendChild(done);
    const open = document.createElement("button");
    open.className = "btn-ghost";
    open.style.marginTop = "8px";
    open.textContent = "View in JobPilot";
    open.addEventListener("click", () => {
      void browser.tabs.create({ url: `${state.serverUrl}/listings` });
    });
    card.appendChild(open);
  } catch (e) {
    err.textContent = e instanceof Error ? e.message : "Save failed";
    err.style.display = "block";
    save.disabled = false;
    save.textContent = "Save to JobPilot";
  }
}

// --- Fill this form -------------------------------------------------------
// The other half of "one click": the user is on an application form and wants
// their own answers in it. Nothing is submitted — they press the button.

async function renderAutofill(): Promise<void> {
  const card = document.createElement("div");
  card.className = "card";
  const shortcut = await autofillShortcut();
  card.innerHTML = `
    <div class="capture-head"><b>Fill this form</b></div>
    <div class="muted small">
      Uses the answers you entered in JobPilot. Nothing is submitted, and any
      CAPTCHA or verification stays yours to finish.
    </div>
    <div class="error" id="fill-err" style="display:none"></div>
    <button class="btn-primary" id="fill" style="margin-top:8px">Fill this form</button>
    <div class="muted small" style="margin-top:6px">
      ${shortcut ? `Shortcut: <b>${shortcut}</b>` : "No shortcut is set — assign one in your browser's extension shortcuts."}
    </div>`;
  app.appendChild(card);

  const button = card.querySelector<HTMLButtonElement>("#fill")!;
  const err = card.querySelector<HTMLElement>("#fill-err")!;
  button.addEventListener("click", () => {
    void (async () => {
      err.style.display = "none";
      button.disabled = true;
      button.textContent = "Filling…";
      try {
        const [tab] = await browser.tabs.query({ active: true, currentWindow: true });
        if (tab?.id == null) throw new Error("No active tab");
        await browser.tabs.sendMessage(tab.id, { type: "bg.autofillNow" });
        // The page shows its own result banner; close so the user can see it.
        window.close();
      } catch {
        err.textContent =
          "JobPilot can't reach this tab. Reload the page and try again — tabs opened before the extension was installed aren't connected yet.";
        err.style.display = "block";
        button.disabled = false;
        button.textContent = "Fill this form";
      }
    })();
  });
}

/** The user's actual binding, which may differ from the suggested one. */
async function autofillShortcut(): Promise<string> {
  try {
    const commands = await browser.commands.getAll();
    return commands.find((c) => c.name === "autofill-form")?.shortcut || "";
  } catch {
    return "";
  }
}

async function renderPaired(state: StoredState, online: boolean): Promise<void> {
  await renderAutofill();
  renderCapture(state);

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
