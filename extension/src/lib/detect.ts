// Form-field discovery in the content script. Read-only: it inspects the DOM
// and produces field descriptors; it never fills or clicks.
import type { DetectedField } from "./types";

export interface LiveField extends DetectedField {
  el: HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement;
}

function labelFor(el: HTMLElement): string {
  const aria = el.getAttribute("aria-label");
  if (aria) return aria.trim();
  const labelledby = el.getAttribute("aria-labelledby");
  if (labelledby) {
    const parts = labelledby
      .split(/\s+/)
      .map((id) => document.getElementById(id)?.textContent?.trim() || "")
      .filter(Boolean);
    if (parts.length) return parts.join(" ");
  }
  if (el.id) {
    const explicit = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
    if (explicit) return (explicit as HTMLElement).innerText.trim();
  }
  const wrap = el.closest("label");
  if (wrap) return wrap.innerText.trim();
  const fieldset = el.closest("fieldset");
  if (fieldset) {
    const legend = fieldset.querySelector("legend");
    if (legend) return legend.textContent?.trim() || "";
  }
  const placeholder = (el as HTMLInputElement).placeholder;
  if (placeholder) return placeholder.trim();
  return el.getAttribute("name") || "";
}

function surrounding(el: HTMLElement): string {
  const container = el.closest("div, fieldset, section, li") || el.parentElement;
  return container ? (container as HTMLElement).innerText.slice(0, 400) : "";
}

function visible(el: HTMLElement): boolean {
  if ((el as HTMLInputElement).disabled) return false;
  const style = getComputedStyle(el);
  if (style.display === "none" || style.visibility === "hidden") return false;
  return el.offsetParent !== null || style.position === "fixed";
}

export function discoverFields(): LiveField[] {
  const fields: LiveField[] = [];
  const radioGroups = new Map<string, { field: LiveField; options: Set<string> }>();
  let counter = 0;

  const controls = document.querySelectorAll<HTMLElement>(
    "input:not([type=hidden]):not([type=submit]):not([type=button]):not([type=reset]), textarea, select",
  );

  controls.forEach((raw) => {
    if (!visible(raw)) return;
    const el = raw as HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement;
    const tag = el.tagName;
    let type: string =
      tag === "TEXTAREA" ? "textarea" : tag === "SELECT" ? "select" : (el as HTMLInputElement).type || "text";

    const ref = `jp-${counter++}`;
    el.setAttribute("data-jp-ref", ref);

    let options: string[] = [];
    if (type === "select") {
      options = Array.from((el as HTMLSelectElement).options)
        .map((o) => o.text.trim())
        .filter(Boolean);
    }

    const name = el.getAttribute("name");
    if (type === "radio" && name) {
      const optionLabel =
        (el as HTMLInputElement).value ||
        labelFor(el) ||
        "";
      const existing = radioGroups.get(name);
      if (existing) {
        existing.options.add(optionLabel);
        return;
      }
      const field: LiveField = {
        ref,
        label: labelFor(el),
        field_type: "radio",
        options: [],
        required: (el as HTMLInputElement).required,
        name,
        surrounding_text: surrounding(el),
        el,
      };
      radioGroups.set(name, { field, options: new Set([optionLabel]) });
      fields.push(field);
      return;
    }

    fields.push({
      ref,
      label: labelFor(el),
      field_type: type,
      options,
      required:
        (el as HTMLInputElement).required || el.getAttribute("aria-required") === "true",
      name,
      surrounding_text: surrounding(el),
      el,
    });
  });

  for (const { field, options } of radioGroups.values()) {
    field.options = Array.from(options).filter(Boolean);
    // Better group label: the enclosing fieldset legend.
    const fieldset = field.el.closest("fieldset");
    const legend = fieldset?.querySelector("legend");
    if (legend?.textContent) field.label = legend.textContent.trim();
  }

  return fields;
}

export function findSubmitButton(): HTMLElement | null {
  const explicit = document.querySelector<HTMLElement>(
    "button[type=submit], input[type=submit]",
  );
  if (explicit) return explicit;
  const buttons = Array.from(document.querySelectorAll<HTMLElement>("button, [role=button]"));
  return (
    buttons.find((b) => /submit|apply|send application/i.test(b.textContent || "")) || null
  );
}

export function looksConfirmed(): boolean {
  const text = (document.body?.innerText || "").slice(0, 5000).toLowerCase();
  return [
    "thank you",
    "application received",
    "successfully submitted",
    "we received",
    "confirmation",
    "your application has been",
  ].some((m) => text.includes(m));
}

export function snapshotFields(): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  document.querySelectorAll<HTMLInputElement>("[data-jp-ref]").forEach((el) => {
    const ref = el.getAttribute("data-jp-ref")!;
    const value = el.type === "password" ? "***" : (el.value || "").slice(0, 200);
    out[ref] = { name: el.name || null, value };
  });
  return out;
}
