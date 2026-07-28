// Challenge / login-wall detection for the content script.
//
// DETECTION ONLY. There is no solving, token handling, OCR, audio path, or
// checkbox auto-clicking anywhere in this file or this extension. When a
// challenge is present the fill engine halts all input and routes the page
// to a human. See CAPTCHA_POLICY.md at the repository root — this mirrors the
// backend's app/executor/captcha.py so both executors behave identically.

const SCRIPT_MARKERS = [
  "recaptcha",
  "google.com/recaptcha",
  "gstatic.com/recaptcha",
  "hcaptcha.com",
  "challenges.cloudflare.com",
  "turnstile",
  "arkoselabs",
  "funcaptcha",
  "geetest",
  "friendlycaptcha",
  "px-cdn.net",
  "px-cloud.net",
  "perimeterx",
  "datadome",
  "imperva",
  "incapsula",
];

const TEXT_PATTERNS = [
  /verify (?:that )?you are (?:a )?human/i,
  /unusual activity/i,
  /security check/i,
  /just a moment/i,
  /attention required/i,
  /checking your browser/i,
  /prove you(?:'| a)re not a robot/i,
  /complete the (?:captcha|challenge|security check)/i,
];

const CHALLENGE_SELECTORS =
  "[data-sitekey], .g-recaptcha, .h-captcha, .cf-turnstile, #px-captcha, iframe[src*='recaptcha'], iframe[src*='hcaptcha'], iframe[title*='challenge' i]";

const LOGIN_PATTERNS = [
  /\/log-?in\b/i,
  /\/sign-?in\b/i,
  /\/sso\b/i,
  /\/auth(?:orize|enticate)?\b/i,
  /accounts\.google\.com/i,
  /login\.microsoftonline\.com/i,
  /okta\.com/i,
];

export interface ChallengeResult {
  detected: boolean;
  kind: "challenge" | "login" | null;
  detail: string | null;
}

export function detectChallenge(startUrl: string | null): ChallengeResult {
  // Mid-flow redirect to a login/SSO page: a human logs in personally.
  const alreadyLogin = startUrl ? LOGIN_PATTERNS.some((p) => p.test(startUrl)) : false;
  if (!alreadyLogin && LOGIN_PATTERNS.some((p) => p.test(location.href))) {
    return { detected: true, kind: "login", detail: `login wall: ${location.href}` };
  }

  const sources: string[] = [];
  document.querySelectorAll("script[src], iframe[src]").forEach((el) => {
    sources.push((el.getAttribute("src") || "").toLowerCase());
  });
  for (const src of sources) {
    for (const marker of SCRIPT_MARKERS) {
      if (src.includes(marker)) {
        return { detected: true, kind: "challenge", detail: `provider script: ${marker}` };
      }
    }
  }
  if (document.querySelector(CHALLENGE_SELECTORS)) {
    return { detected: true, kind: "challenge", detail: "challenge element present" };
  }
  const text = (
    document.title +
    " " +
    (document.body ? document.body.innerText.slice(0, 5000) : "")
  ).toLowerCase();
  for (const pattern of TEXT_PATTERNS) {
    if (pattern.test(text)) {
      return { detected: true, kind: "challenge", detail: `text: ${pattern.source}` };
    }
  }
  return { detected: false, kind: null, detail: null };
}

export function challengeCleared(): boolean {
  return !detectChallenge(location.href).detected;
}
