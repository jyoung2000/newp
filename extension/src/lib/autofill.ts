// One-shot autofill of the form the user is looking at, triggered by a click
// in the popup or a keyboard shortcut. Distinct from lib/fill.ts, which drives
// an application JobPilot chose from the queue:
//
//   - no application, no queue, no listing — just this page, right now
//   - it NEVER submits. It fills and stops, and the person presses the button.
//   - a CAPTCHA or verification step halts it before anything is typed
//
// Values come from what the user entered in JobPilot (profile, custom fields,
// saved answers), resolved server-side by the same resolver the queue path
// uses, so knockout questions and EEO fields are treated identically. Anything
// the resolver isn't sure of is left empty and highlighted rather than guessed.
import browser from "webextension-polyfill";
import * as api from "./api";
import { challengeCleared, detectChallenge } from "./challenge";
import { discoverFields, type LiveField } from "./detect";
import { applyResolution, ChallengeHalt } from "./fill";
import * as human from "./humanize";
import { clearOverlay, highlight, showChallengeHalt, showToast } from "./reviewbar";
import type { Resolution } from "./types";

export interface AutofillSummary {
  filled: number;
  needsHuman: number;
  blocked?: "challenge" | "no-fields" | "not-paired";
  detail?: string;
}

/**
 * A field is worth an OCR crop only when the cheap signals produced nothing.
 * detect.ts already tries aria-label, aria-labelledby, label[for], a wrapping
 * label, a fieldset legend, the placeholder and finally the name attribute —
 * so reaching here means the field is genuinely unnamed in the DOM, which in
 * practice means a canvas-drawn or icon-only control.
 */
function needsOcr(field: LiveField): boolean {
  if (field.name && field.name.trim()) return false;
  const label = (field.label || "").trim();
  if (label.length >= 2) return false;
  // Nothing to type into a button-like control, so don't spend a crop on it.
  return field.field_type !== "checkbox" && field.field_type !== "radio";
}

/**
 * Ask the background to crop the visible tab around this field, then ask the
 * server to read it. Best-effort by design: if the crop fails, the model isn't
 * configured, or offline mode is on, the field simply stays unlabelled and
 * goes to the human.
 */
async function ocrLabel(field: LiveField): Promise<string> {
  const rect = field.el.getBoundingClientRect();
  if (rect.width < 4 || rect.height < 4) return "";
  try {
    const reply = (await browser.runtime.sendMessage({
      type: "capture.crop",
      rect: {
        // A label usually sits above or to the left, so include a margin
        // rather than only the input box itself.
        x: Math.max(0, rect.left - 8),
        y: Math.max(0, rect.top - 44),
        width: rect.width + 16,
        height: rect.height + 52,
      },
      dpr: window.devicePixelRatio || 1,
    })) as { imageB64?: string } | undefined;
    if (!reply?.imageB64) return "";
    const res = await api.ocrLabel(reply.imageB64, field.surrounding_text.slice(0, 200));
    return res.text || "";
  } catch {
    return "";
  }
}

export async function autofillThisPage(): Promise<AutofillSummary> {
  const state = await api.getState();
  if (!state.paired) return { filled: 0, needsHuman: 0, blocked: "not-paired" };

  const startUrl = location.href;

  // Before touching anything: if the page is challenging the user, stop. This
  // is the same rule the queue path enforces — software never answers a
  // CAPTCHA or a verification step, and it does not type around one either.
  const challenge = detectChallenge(startUrl);
  if (challenge.detected) {
    showChallengeHalt(
      challenge.detail || "This page is asking for a human. Finish it yourself, then autofill.",
    );
    return {
      filled: 0,
      needsHuman: 0,
      blocked: "challenge",
      detail: challenge.detail || "challenge",
    };
  }

  const fields = discoverFields();
  if (fields.length === 0) return { filled: 0, needsHuman: 0, blocked: "no-fields" };

  // Last-resort labelling, only for the fields that need it.
  const unlabelled = fields.filter(needsOcr);
  if (unlabelled.length > 0) {
    showToast(`Reading ${unlabelled.length} unlabelled field${unlabelled.length > 1 ? "s" : ""}…`);
    for (const field of unlabelled) {
      const text = await ocrLabel(field);
      if (text) {
        field.label = text;
        field.ocr_label = true;
      }
    }
  }

  const resp = await api.autofill({
    url: startUrl,
    title: document.title,
    fields: fields.map((f) => ({
      ref: f.ref,
      label: f.label,
      field_type: f.field_type,
      options: f.options,
      required: f.required,
      name: f.name,
      surrounding_text: f.surrounding_text,
    })),
  });

  const byRef = new Map(resp.resolutions.map((r) => [r.ref, r] as const));
  // Honour the user's "type like a human" preference here too: a page that
  // reacts badly to instant programmatic input reacts the same way whichever
  // path filled it.
  const profile = state.humanizeOverride === false ? human.INSTANT : human.HUMANIZED;

  let filled = 0;
  let needsHuman = 0;
  for (const field of fields) {
    const resolution: Resolution | undefined = byRef.get(field.ref);
    if (!resolution) continue;
    if (resolution.status === "resolved") {
      try {
        await applyResolution(field, resolution, profile, startUrl);
        filled += 1;
        highlight(field.el, "ok");
        if (profile.keyMaxMs > 0) await human.fieldGap(profile);
      } catch (e) {
        if (e instanceof ChallengeHalt) {
          // A challenge appeared part-way through. Stop where we are and hand
          // over; what is already typed stays for the user to check.
          showChallengeHalt(e.detail);
          return { filled, needsHuman, blocked: "challenge", detail: e.detail };
        }
        throw e;
      }
    } else if (resolution.status === "leave_blank") {
      continue;
    } else {
      // needs_human / draft_pending: highlight, type nothing. A knockout
      // answer or an EEO question is the user's to give, not ours to infer.
      needsHuman += 1;
      highlight(field.el, "human");
    }
  }

  const parts = [`Filled ${filled}`];
  if (needsHuman > 0) parts.push(`${needsHuman} need you (highlighted)`);
  parts.push("nothing was submitted");
  showToast(parts.join(" · "));
  return { filled, needsHuman };
}

export { challengeCleared, clearOverlay };
