// Humanized input: fills form fields the way a person would — the full native
// event chain, human-paced when enabled, and always REAL events even in
// instant mode so controlled React/Vue/Angular components register the input.
//
// This is NOT cloaking. There is no fingerprint spoofing, no navigator.webdriver
// patching, no stealth anything (the architectural test enforces that). The
// extension already runs in the user's real browser and real session — which
// is the honest reason detection is rarely an issue here. See README §3.

export interface TimingProfile {
  keyMinMs: number;
  keyMaxMs: number;
  pauseChance: number;
  pauseMinMs: number;
  pauseMaxMs: number;
  fieldGapMinMs: number;
  fieldGapMaxMs: number;
}

export const HUMANIZED: TimingProfile = {
  keyMinMs: 60,
  keyMaxMs: 180,
  pauseChance: 0.06,
  pauseMinMs: 350,
  pauseMaxMs: 1200,
  fieldGapMinMs: 2000,
  fieldGapMaxMs: 8000,
};

export const INSTANT: TimingProfile = {
  keyMinMs: 0,
  keyMaxMs: 0,
  pauseChance: 0,
  pauseMinMs: 0,
  pauseMaxMs: 0,
  fieldGapMinMs: 50,
  fieldGapMaxMs: 150,
};

const rand = (min: number, max: number) => min + Math.random() * (max - min);
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

function keyDelay(p: TimingProfile): number {
  if (Math.random() < p.pauseChance) return rand(p.pauseMinMs, p.pauseMaxMs);
  return rand(p.keyMinMs, p.keyMaxMs);
}

// React overrides the value setter on inputs; set through the native
// prototype setter so the framework's onChange actually fires.
function setNativeValue(el: HTMLInputElement | HTMLTextAreaElement, value: string): void {
  const proto = el instanceof HTMLTextAreaElement
    ? HTMLTextAreaElement.prototype
    : HTMLInputElement.prototype;
  const setter = Object.getOwnPropertyDescriptor(proto, "value")?.set;
  if (setter) setter.call(el, value);
  else el.value = value;
}

function fireKey(el: Element, type: string, key: string): void {
  el.dispatchEvent(
    new KeyboardEvent(type, { key, bubbles: true, cancelable: true }),
  );
}

async function scrollFocus(el: HTMLElement, p: TimingProfile): Promise<void> {
  el.scrollIntoView({ behavior: p.keyMaxMs > 0 ? "smooth" : "auto", block: "center" });
  if (p.keyMaxMs > 0) await sleep(rand(150, 400));
  el.focus();
  el.dispatchEvent(new FocusEvent("focus", { bubbles: true }));
}

export async function typeText(
  el: HTMLInputElement | HTMLTextAreaElement,
  value: string,
  p: TimingProfile,
): Promise<void> {
  await scrollFocus(el, p);
  setNativeValue(el, "");
  el.dispatchEvent(new Event("input", { bubbles: true }));

  if (p.keyMaxMs <= 0) {
    setNativeValue(el, value);
    el.dispatchEvent(new InputEvent("beforeinput", { bubbles: true, data: value }));
    el.dispatchEvent(new Event("input", { bubbles: true }));
  } else {
    let current = "";
    for (const ch of value) {
      fireKey(el, "keydown", ch);
      el.dispatchEvent(new InputEvent("beforeinput", { bubbles: true, data: ch }));
      current += ch;
      setNativeValue(el, current);
      el.dispatchEvent(new InputEvent("input", { bubbles: true, data: ch }));
      fireKey(el, "keyup", ch);
      await sleep(keyDelay(p));
    }
  }
  el.dispatchEvent(new Event("change", { bubbles: true }));
  el.blur();
  el.dispatchEvent(new FocusEvent("blur", { bubbles: true }));
}

export async function selectOption(
  el: HTMLSelectElement,
  optionText: string,
  p: TimingProfile,
): Promise<boolean> {
  await scrollFocus(el, p);
  const options = Array.from(el.options);
  const match =
    options.find((o) => o.text.trim().toLowerCase() === optionText.trim().toLowerCase()) ||
    options.find((o) => o.text.trim().toLowerCase().includes(optionText.trim().toLowerCase()));
  if (!match) return false;
  el.value = match.value;
  el.dispatchEvent(new Event("input", { bubbles: true }));
  el.dispatchEvent(new Event("change", { bubbles: true }));
  return true;
}

export async function setCheckbox(
  el: HTMLInputElement,
  checked: boolean,
  p: TimingProfile,
): Promise<void> {
  await scrollFocus(el, p);
  if (el.checked !== checked) {
    el.click(); // a real click through the native path
  }
  if (el.checked !== checked) {
    // Some frameworks intercept click; set + dispatch as a fallback.
    el.checked = checked;
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
  }
}

export async function chooseRadio(
  name: string,
  value: string,
  root: ParentNode,
  p: TimingProfile,
): Promise<boolean> {
  const radios = Array.from(
    root.querySelectorAll<HTMLInputElement>(`input[type=radio][name="${CSS.escape(name)}"]`),
  );
  let target = radios.find((r) => r.value.trim().toLowerCase() === value.trim().toLowerCase());
  if (!target) {
    // Match by associated label text.
    target = radios.find((r) => {
      const label = r.closest("label") || root.querySelector(`label[for="${r.id}"]`);
      return label ? label.textContent?.trim().toLowerCase() === value.trim().toLowerCase() : false;
    });
  }
  if (!target) return false;
  await scrollFocus(target, p);
  target.click();
  if (!target.checked) {
    target.checked = true;
    target.dispatchEvent(new Event("input", { bubbles: true }));
    target.dispatchEvent(new Event("change", { bubbles: true }));
  }
  return true;
}

export async function fieldGap(p: TimingProfile): Promise<void> {
  await sleep(rand(p.fieldGapMinMs, p.fieldGapMaxMs));
}
