// Typed client for the JobPilot backend, authenticated by the device token.
import browser from "webextension-polyfill";
import type {
  DetectedField,
  InterventionRequest,
  InterventionState,
  NextJobResponse,
  ResolveResponse,
  StoredState,
} from "./types";

const DEFAULTS: StoredState = {
  serverUrl: "http://localhost:1456",
  token: null,
  deviceId: null,
  userEmail: null,
  paired: false,
  humanizeOverride: null,
  debuggerRelayOptIn: false,
};

export async function getState(): Promise<StoredState> {
  const stored = (await browser.storage.local.get(
    DEFAULTS as unknown as Record<string, unknown>,
  )) as Partial<StoredState>;
  return { ...DEFAULTS, ...stored };
}

export async function setState(patch: Partial<StoredState>): Promise<void> {
  await browser.storage.local.set(patch);
}

async function authed(path: string, init: RequestInit = {}): Promise<Response> {
  const state = await getState();
  if (!state.token) throw new Error("Not paired");
  const headers = new Headers(init.headers);
  headers.set("Authorization", `Bearer ${state.token}`);
  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  return fetch(`${state.serverUrl}${path}`, { ...init, headers });
}

export interface PairResult {
  token: string;
  device_id: number;
  user_email: string;
  server_version: string;
}

export async function pair(
  serverUrl: string,
  code: string,
  name: string,
  browserName: string,
): Promise<PairResult> {
  const res = await fetch(`${serverUrl}/api/ext/pair`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      code,
      name,
      browser: browserName,
      extension_version: browser.runtime.getManifest().version,
    }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: "Pairing failed" }));
    throw new Error(body.detail || `Pairing failed (${res.status})`);
  }
  return (await res.json()) as PairResult;
}

export interface PingResult {
  ok: boolean;
  user_email: string;
  device_id: number;
  device_name: string;
  server_version: string;
  latest_extension_version: string | null;
}

export async function ping(): Promise<PingResult> {
  const res = await authed("/api/ext/ping");
  if (!res.ok) throw new Error(`ping failed ${res.status}`);
  return (await res.json()) as PingResult;
}

export async function nextJob(): Promise<NextJobResponse> {
  const res = await authed("/api/ext/next-job", { method: "POST" });
  if (!res.ok) throw new Error(`next-job failed ${res.status}`);
  return (await res.json()) as NextJobResponse;
}

export async function resolveFields(
  applicationId: number,
  fields: DetectedField[],
): Promise<ResolveResponse> {
  const res = await authed(`/api/ext/applications/${applicationId}/resolve`, {
    method: "POST",
    body: JSON.stringify({ fields }),
  });
  if (!res.ok) throw new Error(`resolve failed ${res.status}`);
  return (await res.json()) as ResolveResponse;
}

export async function createInterventions(
  applicationId: number,
  items: InterventionRequest[],
  reason: string,
): Promise<number[]> {
  const res = await authed(`/api/ext/applications/${applicationId}/interventions`, {
    method: "POST",
    body: JSON.stringify({ items, reason }),
  });
  if (!res.ok) throw new Error(`interventions failed ${res.status}`);
  return ((await res.json()) as { intervention_ids: number[] }).intervention_ids;
}

export async function listInterventions(
  applicationId: number,
): Promise<InterventionState[]> {
  const res = await authed(`/api/ext/applications/${applicationId}/interventions`);
  if (!res.ok) throw new Error(`list interventions failed ${res.status}`);
  return (await res.json()) as InterventionState[];
}

export async function setStatus(
  applicationId: number,
  status: string,
  reason?: string,
  error?: string,
): Promise<void> {
  const res = await authed(`/api/ext/applications/${applicationId}/status`, {
    method: "POST",
    body: JSON.stringify({ status, reason, error }),
  });
  if (!res.ok) throw new Error(`set status failed ${res.status}`);
}

export async function submitResult(
  applicationId: number,
  confirmed: boolean,
  snapshot: Record<string, unknown>,
  screenshotB64?: string,
): Promise<void> {
  const res = await authed(`/api/ext/applications/${applicationId}/submit-result`, {
    method: "POST",
    body: JSON.stringify({
      confirmed,
      field_snapshot: snapshot,
      screenshot_b64: screenshotB64,
    }),
  });
  if (!res.ok) throw new Error(`submit-result failed ${res.status}`);
}

export async function downloadResolvedFile(fileUrl: string): Promise<Blob> {
  const res = await authed(fileUrl);
  if (!res.ok) throw new Error(`file download failed ${res.status}`);
  return await res.blob();
}
