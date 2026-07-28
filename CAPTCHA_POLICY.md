# JobPilot CAPTCHA & human-verification policy

**A human being personally completes every CAPTCHA, bot check, or
"verify you're human" challenge. Always. No exceptions.**

A CAPTCHA is a website asking *"is a person here?"* When JobPilot is running,
the honest answer must remain **yes** — because the person is here: they are
the applicant, and the software is only their typist.

## What JobPilot never does

- **No solver services.** There is no integration with any CAPTCHA-solving
  service — no client, no configuration key, no commented-out stub. A build-time
  architectural test (`backend/tests/test_captcha_policy.py`) fails the build if
  any known solver-service SDK or domain appears in the source tree or the
  dependency manifests.
- **No recognition path aimed at a challenge.** No OCR, no ML classification,
  no audio transcription pointed at a challenge of any kind.
- **No token replay.** A solved challenge is never reused across sessions,
  jobs, or forms.
- **No auto-clicking checkbox challenges**, including "I'm not a robot",
  whether interest-based or otherwise.
- **No cloaking.** JobPilot does not spoof browser fingerprints, patch
  `navigator.webdriver`, inject canvas/WebGL noise, rotate proxies, or use
  stealth plugins. The same architectural test bans that tooling too.

## What happens instead — every time

1. The executor detects a challenge or login wall (reCAPTCHA, hCaptcha,
   Turnstile, Arkose/FunCaptcha, GeeTest, Friendly Captcha, Cloudflare /
   PerimeterX / DataDome / Imperva interstitials, "verify you are human" /
   "unusual activity" text, a mid-flow redirect to login/SSO, or any element
   with `data-sitekey`) and **immediately halts all typing and clicking** on
   that page.
2. The application transitions to `needs_human` with reason `challenge`.
   Software enters nothing further on that page.
3. The user is notified everywhere at once: extension badge and browser
   notification, the JobPilot UI live over WebSocket, and optional email or
   webhook.
4. The user personally completes the challenge in a real, visible page —
   locally in their own browser tab, or remotely through the session relay
   (noVNC for the server browser; an opt-in `chrome.debugger` screencast for
   the extension). **The relay transports the human's own taps and
   keystrokes; it never generates input.**
5. The executor verifies the challenge element is genuinely gone, re-verifies
   the form state is intact, and only then resumes.
6. If the user doesn't respond within the configured window (default
   30 minutes), the job parks as `needs_human (waiting)` and the runner moves
   on to the next job. **A timeout never becomes an automatic attempt.**

Every detection is logged, so the user can see which sites challenge them.

## Why this is non-negotiable

CAPTCHAs are the one place a website explicitly asks to interact with a
person. Automating past that ask — by machine solving, by paying a solving
farm, or by disguising the automation — would make every JobPilot
application dishonest at the exact moment the employer asked for honesty.
This project would rather park a job application indefinitely than answer
that question falsely once.

The same principle covers answers: JobPilot never answers a question the
user hasn't effectively answered (see the resolver's knockout rules in
`backend/app/services/resolver.py`).
