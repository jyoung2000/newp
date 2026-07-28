// Opt-in remote-hand relay for solving a CAPTCHA from another device.
//
// THE RELAY CARRIES A HUMAN'S REAL INPUT AND GENERATES NONE OF ITS OWN.
// When the user is away from this browser, they can — with an explicit
// permission grant — drive the real page from the container UI: their actual
// taps and keystrokes are transported here and dispatched to the tab via the
// Chrome DevTools Protocol (Input.dispatchMouseEvent / dispatchKeyEvent).
// JobPilot never synthesizes an interaction; if the debugger permission is
// declined, or on Firefox where this isn't available, the job simply parks as
// "needs_human (at browser)" for the user to finish when they return.
//
// This module contains NO challenge-solving logic. It is a transport for
// Page.startScreencast frames (out) and human input events (in). There is no
// OCR, no token handling, no automated clicking.
import browser from "webextension-polyfill";

const DEBUGGER_VERSION = "1.3";

export interface RelayHumanInput {
  // Exactly one real human action, forwarded from the container UI.
  kind: "mouse" | "key";
  event: Record<string, unknown>;
}

export async function hasDebuggerPermission(): Promise<boolean> {
  try {
    return await browser.permissions.contains(({ permissions: ["debugger"] } as unknown as browser.Permissions.Permissions));
  } catch {
    return false;
  }
}

export async function requestDebuggerPermission(): Promise<boolean> {
  // Requested optionally, at first use, with a plain-English explanation
  // shown by the popup before this is called.
  try {
    return await browser.permissions.request(({ permissions: ["debugger"] } as unknown as browser.Permissions.Permissions));
  } catch {
    return false;
  }
}

// Chrome-only. The presence of chrome.debugger is checked at runtime.
function chromeDebugger(): typeof chrome.debugger | null {
  const c = (globalThis as unknown as { chrome?: typeof chrome }).chrome;
  return c?.debugger ?? null;
}

export class TabRelay {
  private target: { tabId: number };
  private attached = false;

  constructor(tabId: number) {
    this.target = { tabId };
  }

  static available(): boolean {
    return chromeDebugger() !== null;
  }

  async start(onFrame: (dataB64: string, metadata: unknown) => void): Promise<void> {
    const dbg = chromeDebugger();
    if (!dbg) throw new Error("chrome.debugger unavailable (Firefox: finish at the browser)");
    await new Promise<void>((resolve, reject) =>
      dbg.attach(this.target, DEBUGGER_VERSION, () =>
        chrome.runtime.lastError ? reject(new Error(chrome.runtime.lastError.message)) : resolve(),
      ),
    );
    this.attached = true;
    dbg.onEvent.addListener((source, method, params) => {
      if (source.tabId !== this.target.tabId) return;
      if (method === "Page.screencastFrame") {
        const p = params as { data: string; sessionId: number; metadata: unknown };
        onFrame(p.data, p.metadata);
        dbg.sendCommand(this.target, "Page.screencastFrameAck", { sessionId: p.sessionId });
      }
    });
    await this.send("Page.enable", {});
    await this.send("Page.startScreencast", { format: "jpeg", quality: 60, everyNthFrame: 1 });
  }

  // Forward ONE human input event to the real page. This is the remote hand.
  async forwardInput(input: RelayHumanInput): Promise<void> {
    if (!this.attached) return;
    if (input.kind === "mouse") {
      await this.send("Input.dispatchMouseEvent", input.event);
    } else if (input.kind === "key") {
      await this.send("Input.dispatchKeyEvent", input.event);
    }
  }

  async stop(): Promise<void> {
    const dbg = chromeDebugger();
    if (!dbg || !this.attached) return;
    try {
      await this.send("Page.stopScreencast", {});
    } catch {
      /* ignore */
    }
    await new Promise<void>((resolve) => dbg.detach(this.target, () => resolve()));
    this.attached = false;
  }

  private send(method: string, params: object): Promise<unknown> {
    const dbg = chromeDebugger();
    if (!dbg) return Promise.reject(new Error("no debugger"));
    return new Promise((resolve, reject) =>
      dbg.sendCommand(this.target, method, params, (result) =>
        chrome.runtime.lastError ? reject(new Error(chrome.runtime.lastError.message)) : resolve(result),
      ),
    );
  }
}
