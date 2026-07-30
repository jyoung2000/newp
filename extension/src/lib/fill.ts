// The fill orchestrator. Discovers fields, resolves them through the server
// (the SAME resolver the Playwright executor uses), applies resolved values
// with the humanized engine, and — the core invariant — checks for a
// challenge continuously, halting all input the instant one appears and
// routing it to the human. It never solves anything.

import * as api from "./api";
import { challengeCleared, detectChallenge } from "./challenge";
import { discoverFields, findSubmitButton, looksConfirmed, snapshotFields, type LiveField } from "./detect";
import * as human from "./humanize";
import { clearOverlay, highlight, showChallengeHalt, showReviewBar, showToast, type ReviewItem } from "./reviewbar";
import type { InterventionRequest, NextJob, Resolution } from "./types";

export class ChallengeHalt extends Error {
  constructor(
    public detail: string,
    public kind: string,
  ) {
    super(detail);
  }
}

async function screenshotDataUrl(): Promise<string | undefined> {
  // The content script can't capture the tab; the background does that via
  // chrome.tabs.captureVisibleTab. We request it through a message.
  try {
    const browser = (await import("webextension-polyfill")).default;
    const result = (await browser.runtime.sendMessage({ type: "capture" })) as
      | { dataUrl?: string }
      | undefined;
    if (result?.dataUrl) return result.dataUrl.split(",")[1];
  } catch {
    /* capture is best-effort */
  }
  return undefined;
}

export function guard(startUrl: string): void {
  const check = detectChallenge(startUrl);
  if (check.detected) throw new ChallengeHalt(check.detail || "challenge", check.kind || "challenge");
}

export async function applyResolution(
  field: LiveField,
  resolution: Resolution,
  profile: human.TimingProfile,
  startUrl: string,
): Promise<void> {
  guard(startUrl); // re-check immediately before touching the DOM
  const value = resolution.formatted ?? String(resolution.value ?? "");

  if (resolution.kind === "file" && resolution.file_url) {
    const blob = await api.downloadResolvedFile(resolution.file_url);
    const file = new File([blob], resolution.file_name || "resume", {
      type: blob.type || "application/octet-stream",
    });
    const input = field.el as HTMLInputElement;
    const dt = new DataTransfer();
    dt.items.add(file);
    input.files = dt.files;
    input.dispatchEvent(new Event("input", { bubbles: true }));
    input.dispatchEvent(new Event("change", { bubbles: true }));
    return;
  }
  if (resolution.auto_check) {
    await human.setCheckbox(field.el as HTMLInputElement, true, profile);
    return;
  }
  switch (field.field_type) {
    case "select":
      await human.selectOption(field.el as HTMLSelectElement, value, profile);
      break;
    case "radio":
      await human.chooseRadio(field.name || field.ref, value, document, profile);
      break;
    case "checkbox": {
      const truthy = ["true", "yes", "1"].includes(value.toLowerCase());
      await human.setCheckbox(field.el as HTMLInputElement, truthy, profile);
      break;
    }
    default:
      await human.typeText(field.el as HTMLInputElement | HTMLTextAreaElement, value, profile);
  }
}

export interface FillResult {
  outcome: "needs_human" | "review" | "drafted" | "submitted" | "submitted_unconfirmed" | "stopped";
  interventions?: InterventionRequest[];
  reason?: string;
  snapshot?: Record<string, unknown>;
  screenshot?: string;
  confirmed?: boolean;
}

// Runs one job on the current page. `stopped()` lets the caller abort a run
// between fields, leaving no half-submitted form.
export async function runFill(
  job: NextJob,
  stopped: () => boolean,
): Promise<FillResult> {
  const startUrl = location.href;
  guard(startUrl);
  const profile = job.humanize ? human.HUMANIZED : human.INSTANT;
  const fields = discoverFields();

  const unresolved: InterventionRequest[] = [];
  const reviewItems: ReviewItem[] = [];
  const reviewFields: { field: LiveField; resolution: Resolution }[] = [];

  // Resolve in one round-trip through the server-side resolver.
  const resp = await api.resolveFields(
    job.application_id,
    fields.map((f) => ({
      ref: f.ref,
      label: f.label,
      field_type: f.field_type,
      options: f.options,
      required: f.required,
      name: f.name,
      surrounding_text: f.surrounding_text,
    })),
  );
  const byRef = new Map(resp.resolutions.map((r) => [r.ref, r] as const));

  for (const field of fields) {
    if (stopped()) return { outcome: "stopped" };
    guard(startUrl);
    const resolution = byRef.get(field.ref);
    if (!resolution) continue;

    if (resolution.status === "resolved") {
      if (job.mode === "review") {
        reviewFields.push({ field, resolution });
        reviewItems.push({
          ref: field.ref,
          label: field.label,
          value: resolution.formatted ?? String(resolution.value ?? ""),
          source: `from ${resolution.source}`,
          editable: field.field_type === "text" || field.field_type === "textarea",
        });
        highlight(field.el, "ok");
      } else {
        try {
          await applyResolution(field, resolution, profile, startUrl);
        } catch (e) {
          if (e instanceof ChallengeHalt) throw e;
          throw e;
        }
        if (profile.keyMaxMs > 0) await human.fieldGap(profile);
      }
    } else if (resolution.status === "leave_blank") {
      // Deliberately blank (e.g. current compensation) — do nothing.
      continue;
    } else {
      // needs_human or draft_pending
      highlight(field.el, "human");
      unresolved.push({
        kind: resolution.draft ? "draft_approval" : "unknown_field",
        question: field.label,
        field_meta: {
          label: field.label,
          field_type: field.field_type,
          options: field.options,
          required: field.required,
          reason: resolution.reason,
          is_knockout: resolution.is_knockout,
          is_eeo: resolution.is_eeo,
          draft: resolution.draft,
          ref: field.ref,
        },
      });
    }
  }

  if (unresolved.length > 0) {
    const shot = await screenshotDataUrl();
    if (shot) unresolved[unresolved.length - 1].screenshot_b64 = shot;
    return { outcome: "needs_human", interventions: unresolved, reason: "unknown_field" };
  }

  // Review mode: fill the highlighted values only after approval.
  if (job.mode === "review") {
    const decision = await showReviewBar(reviewItems);
    clearOverlay();
    if (decision.action === "skip") {
      return { outcome: "needs_human", reason: "review", interventions: [] };
    }
    const edits = decision.action === "edit" ? decision.values : {};
    for (const { field, resolution } of reviewFields) {
      if (stopped()) return { outcome: "stopped" };
      const override = edits[field.ref];
      const applied = override !== undefined ? { ...resolution, formatted: override, value: override } : resolution;
      await applyResolution(field, applied, profile, startUrl);
    }
    // After approval in review mode we submit.
  }

  if (job.mode === "draft") {
    const shot = await screenshotDataUrl();
    showToast("Draft ready — review and submit it yourself.");
    return { outcome: "drafted", snapshot: snapshotFields(), screenshot: shot };
  }

  // Auto + approved-review: submit.
  if (stopped()) return { outcome: "stopped" };
  guard(startUrl);
  const submit = findSubmitButton();
  const snapshot = snapshotFields();
  if (!submit) {
    return { outcome: "needs_human", reason: "error", interventions: [
      { kind: "error", question: "Could not find a submit button on this page", field_meta: {} },
    ] };
  }
  submit.click();
  await new Promise((r) => setTimeout(r, 2500));
  guard(startUrl);
  const shot = await screenshotDataUrl();
  const confirmed = looksConfirmed();
  return {
    outcome: confirmed ? "submitted" : "submitted_unconfirmed",
    confirmed,
    snapshot,
    screenshot: shot,
  };
}

export { challengeCleared, showChallengeHalt, clearOverlay };
