"""Challenge and login-wall detection.

Detection only. There is deliberately no solving, token handling, or
bypass logic anywhere in this module or this codebase — see
CAPTCHA_POLICY.md at the repository root. When anything here matches, the
executor halts all input on the page and hands the session to a human.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# Domains/scripts that indicate a challenge provider is present on the page.
CHALLENGE_SCRIPT_MARKERS = [
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
]

# Visible-text patterns of interstitials and inline challenges.
CHALLENGE_TEXT_PATTERNS = [
    r"verify (?:that )?you are (?:a )?human",
    r"unusual activity",
    r"security check",
    r"just a moment",
    r"attention required",
    r"checking your browser",
    r"prove you(?:'| a)re not a robot",
    r"complete the (?:captcha|challenge|security check)",
]

LOGIN_URL_PATTERNS = [
    r"/log-?in\b",
    r"/sign-?in\b",
    r"/sso\b",
    r"/auth(?:orize|enticate)?\b",
    r"accounts\.google\.com",
    r"login\.microsoftonline\.com",
    r"okta\.com",
]

_TEXT_RE = re.compile("|".join(CHALLENGE_TEXT_PATTERNS), re.IGNORECASE)
_LOGIN_RE = re.compile("|".join(LOGIN_URL_PATTERNS), re.IGNORECASE)


@dataclass
class ChallengeCheck:
    detected: bool
    kind: str | None = None  # challenge / login
    detail: str | None = None


# Evaluated in the page. Returns {detected, kind, detail}. Read-only DOM
# inspection — it never clicks, fills, or mutates anything.
DETECTION_JS = r"""
() => {
  const markers = %MARKERS%;
  const sources = [];
  for (const el of document.querySelectorAll('script[src], iframe[src]')) {
    sources.push(el.getAttribute('src') || '');
  }
  for (const src of sources) {
    const lowered = src.toLowerCase();
    for (const marker of markers) {
      if (lowered.includes(marker)) {
        return { detected: true, kind: 'challenge', detail: 'script/iframe: ' + marker };
      }
    }
  }
  if (document.querySelector('[data-sitekey], .g-recaptcha, .h-captcha, .cf-turnstile, #px-captcha')) {
    return { detected: true, kind: 'challenge', detail: 'challenge element present' };
  }
  const text = (document.title + ' ' + (document.body ? document.body.innerText.slice(0, 5000) : '')).toLowerCase();
  const patterns = %PATTERNS%;
  for (const p of patterns) {
    if (new RegExp(p, 'i').test(text)) {
      return { detected: true, kind: 'challenge', detail: 'text: ' + p };
    }
  }
  return { detected: false, kind: null, detail: null };
}
""".replace("%MARKERS%", repr(CHALLENGE_SCRIPT_MARKERS)).replace(
    "%PATTERNS%", repr([p.replace("\\", "\\\\") for p in CHALLENGE_TEXT_PATTERNS])
)


def check_html(html: str, title: str = "") -> ChallengeCheck:
    """Server-side check of raw HTML (used in tests and non-JS contexts)."""
    lowered = html.lower()
    for marker in CHALLENGE_SCRIPT_MARKERS:
        if marker in lowered:
            return ChallengeCheck(True, "challenge", f"marker: {marker}")
    if re.search(r"data-sitekey\s*=", lowered):
        return ChallengeCheck(True, "challenge", "data-sitekey attribute")
    if _TEXT_RE.search(f"{title}\n{html}"):
        return ChallengeCheck(True, "challenge", "challenge text pattern")
    return ChallengeCheck(False)


def is_login_url(url: str, previous_url: str | None = None) -> bool:
    """A mid-flow redirect to a login/SSO page is treated like a challenge:
    a human logs in personally; software never enters credentials."""
    if previous_url and _LOGIN_RE.search(previous_url):
        return False  # already on a login page when we started
    return bool(_LOGIN_RE.search(url))
