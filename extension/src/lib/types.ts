// Shared types between background, content and popup. These mirror the
// backend's extension API (backend/app/api/extension.py) and message shapes.

export interface StoredState {
  serverUrl: string;
  token: string | null;
  deviceId: number | null;
  userEmail: string | null;
  paired: boolean;
  humanizeOverride: boolean | null; // null = follow the run's setting
  debuggerRelayOptIn: boolean;
}

export interface Listing {
  id: number;
  title: string;
  company: string;
  apply_url: string | null;
  canonical_url: string;
  location: string | null;
}

export interface NextJob {
  application_id: number;
  mode: "auto" | "review" | "draft";
  humanize: boolean;
  resume: boolean;
  listing: Listing;
  intervention_wait_minutes: number;
}

export interface NextJobResponse {
  job: NextJob | null;
  waiting_reason: string | null;
  retry_in_seconds: number;
}

export interface DetectedField {
  ref: string;
  label: string;
  field_type: string;
  options: string[];
  required: boolean;
  name: string | null;
  surrounding_text: string;
}

export interface Resolution {
  ref: string | null;
  label: string;
  status: "resolved" | "leave_blank" | "needs_human" | "draft_pending";
  value: unknown;
  formatted: string | null;
  kind: string;
  source: string;
  confidence: number;
  field_key: string | null;
  is_knockout: boolean;
  is_eeo: boolean;
  auto_check: boolean;
  reason: string;
  draft: string | null;
  file_url: string | null;
  file_name: string | null;
}

export interface ResolveResponse {
  resolutions: Resolution[];
  run_active: boolean;
}

export interface InterventionState {
  id: number;
  kind: string;
  status: string;
  answer: unknown;
  field_meta: Record<string, unknown>;
}

// Messages: content <-> background
export type ContentToBackground =
  | { type: "content.ready"; url: string }
  | { type: "content.progress"; applicationId: number; message: string }
  | { type: "content.needsHuman"; applicationId: number; items: InterventionRequest[]; reason: string }
  | { type: "content.challenge"; applicationId: number; detail: string; kind: string; screenshot?: string }
  | { type: "content.submitted"; applicationId: number; confirmed: boolean; snapshot: Record<string, unknown>; screenshot?: string }
  | { type: "content.status"; applicationId: number; status: string; reason?: string; error?: string }
  | { type: "content.reviewReady"; applicationId: number; screenshot?: string };

export interface InterventionRequest {
  kind: string;
  question: string | null;
  field_meta: Record<string, unknown>;
  screenshot_b64?: string;
}

export type BackgroundToContent =
  | { type: "bg.fillJob"; job: NextJob }
  | { type: "bg.resume"; applicationId: number }
  | { type: "bg.stop" }
  | { type: "bg.interventionsAnswered"; applicationId: number };
