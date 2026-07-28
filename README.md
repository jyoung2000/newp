# JobPilot

A self-hosted job-search assistant you run on your own machine to manage your
own job hunt. It stores your real information once, finds real openings that
match, fills each employer's real application form with your real answers, and
keeps an honest record of what was submitted and when.

JobPilot removes typing, not judgment. **You are the applicant; the software
is the typist.** Three rules run through the whole codebase:

1. **Your answers, never invented.** If your profile says four years of
   Python, the form gets four. A missing required fact stops and asks you —
   and a knockout question is *never* guessed, in any mode, at any confidence.
2. **A human decides every CAPTCHA. Always.** JobPilot detects challenges and
   hands them to you; it never solves, replays, outsources, or auto-clicks
   one. See [`CAPTCHA_POLICY.md`](CAPTCHA_POLICY.md).
3. **Inside what sites permit.** Official/public APIs and the structured data
   employers publish for search engines; polite rate limits and `robots.txt`;
   no scraping of boards that forbid it. See [`docs/SOURCES.md`](docs/SOURCES.md).

---

## Architecture at a glance

One FastAPI origin (UI + REST + WebSocket, port **1456**), an `arq` worker
running a headful Playwright executor, Postgres and Redis — plus a browser
extension that is the second, preferred executor because it runs in *your*
browser with *your* logged-in sessions. Both executors share one field
resolver and one application state machine. Full diagram and lifecycle in
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

```
React SPA ──cookie+WS──▶  app:1456 (FastAPI)  ──▶ Postgres (your data)
Extension ──device token─▶  ▲   │  services/resolver, sources/, llm/, executor/
(your browser) fills the    │   ▼
employer's real form     Redis pub/sub ──▶ worker (Playwright headful + noVNC)
```

---

## Quick start (Docker)

```bash
cp .env.example .env
# Edit .env: set SECRET_KEY (openssl rand -hex 32) and, for real LLM features,
# ANTHROPIC_API_KEY. Without a key JobPilot runs with deterministic offline
# heuristics (LLM_DRY_RUN behavior) and sends nothing to Anthropic.

docker compose up --build
# → open http://localhost:1456
```

Compose builds four services — `app` (:1456), `worker`, `db` (Postgres 16),
`redis` (Redis 7) — with named volumes for Postgres, uploads, and the
Playwright browsers. On first boot the app applies migrations and seeds a
demo user with live listings (falling back to bundled fixtures if the boards
are unreachable), so the UI isn't empty.

**Demo login:** `demo@jobpilot.local` / `demo-password-1234` (created by the
seed; change or delete it in Settings).

### Definition of done — the end-to-end path

`docker compose up` → open `http://localhost:1456` → create an account → build
a profile and confirm the résumé parse → download and install the extension
from Settings and pair it → run a search returning real current listings with
salary, education, post date and summaries → start an auto-apply run on a real
Greenhouse or Lever posting → hit one unknown field and answer it from your
phone via the container UI, watching it save to the knowledge base and the run
resume → confirm a CAPTCHA detection halts the run and routes to you rather
than being handled in software → toggle "Type like a human" and watch the fill
behavior change → see the submission in analytics with its exact timestamp,
field snapshot and confirmation screenshot → export the profile and job list,
re-import, and confirm nothing was lost.

---

## Local development (without Docker)

You need Python 3.12, Node 22, and (for real runs) Postgres + Redis. The test
suite needs neither — it runs against SQLite.

```bash
# Backend
cd backend
uv sync
uv run pytest -q            # 126 tests, no services needed
uv run alembic upgrade head # against $DATABASE_URL
uv run uvicorn app.main:app --reload --port 1456

# Frontend (build into backend/app/static, or run a dev server)
cd ../frontend
npm install
npm run gen:types          # typed client from the OpenAPI schema
npm run build              # → backend/app/static
npm run dev                # or: Vite dev server proxying /api to :1456

# Worker (needs Redis + Playwright browsers)
cd ../backend
uv run playwright install chromium
uv run arq app.workers.main.WorkerSettings
```

A `Makefile` wraps the common tasks: `make test`, `make lint`, `make
typecheck`, `make dev`, `make front-build`, `make ext-zip`, `make seed`,
`make up`.

---

## The browser extension

The extension is the default executor for anything interactive: it runs in
your own browser, so it uses your existing logged-in sessions and detection is
rarely an issue — the honest reason being that it *is* you.

### Install

Both bundles are built into the app and offered at **Settings → Extension**:

- **Chrome / Edge:** download `jobpilot-chrome.zip`, unzip it, then
  `chrome://extensions` → enable *Developer mode* → *Load unpacked* → pick the
  unzipped folder. The Settings page shows an illustrated walkthrough.
- **Firefox:** download `jobpilot-firefox.zip`. Permanent installation
  requires either a signed build **or** Developer Edition / ESR with
  `xpinstall.signatures.required=false` in `about:config`. For a quick trial,
  `about:debugging` → *This Firefox* → *Load Temporary Add-on* → pick the zip
  (temporary installs clear on restart). To sign it with your own AMO
  credentials: `make sign-firefox` (needs `WEB_EXT_API_KEY` /
  `WEB_EXT_API_SECRET` from <https://addons.mozilla.org/developers/addon/api/key/>).

Bundles are version-stamped; the popup nudges you when the container has a
newer build.

### Pairing

Settings → Extension shows a one-time **6-digit code** and a QR. Open the
extension popup, enter your JobPilot server URL and the code, and name the
device. The extension exchanges the code for a device token scoped to your
account, kept in `storage.local`. Devices are listed and revocable in
Settings; the popup and the container both show link status.

### "Type like a human"

A per-user default and per-run override. When on, form entry mimics manual
typing — fields scrolled into view and focused, characters entered one at a
time at a variable 60–180 ms cadence with occasional longer pauses, the
complete native event chain fired, `<select>` and custom dropdowns opened and
clicked rather than value-assigned, reading time between fields, randomized
think-time between jobs. When off, fills are instant but still dispatch real
native events.

**Why it exists:** React/Vue/Angular forms and multi-step ATS wizards
frequently ignore programmatic `value` assignment — controlled components only
register state on real event sequences, and many wizards won't enable *Next*
without a valid blur. Human-paced entry is simply the reliable way to fill
these forms correctly, and it paces requests instead of firing a burst.

**What it is not:** it is not cloaking and does not make automation
undetectable. There is no fingerprint spoofing, no `navigator.webdriver`
patching, no canvas/WebGL noise, no stealth plugin, no proxy rotation, no
residential-IP service anywhere in this project — the architectural test
enforces that. CAPTCHAs still go to you, rate limits still apply, and answers
are still your own.

---

## Remote access (hardening)

The UI is fully responsive so you can answer interventions from your phone.
If you expose it beyond `localhost`, set `PUBLIC_URL` (e.g.
`https://jobs.example.com`) — Secure cookies and HSTS turn on automatically
for `https://` origins — and:

- **Turn on TOTP 2FA** (Settings → Security).
- Put JobPilot **behind a reverse proxy** (Caddy/nginx with TLS) **or a
  tailnet** (Tailscale/WireGuard) rather than raw port-forwarding.
- The worker's noVNC viewer (for remote CAPTCHA solving) is bound to
  `127.0.0.1:6080` by default and embedded only inside the authenticated UI —
  do not expose it directly.

---

## Remote CAPTCHA solving — still a human, from anywhere

Every human-verification challenge is completed by a person, even when you're
not at the machine:

- **Playwright executor:** the worker's headful Chromium is shared over noVNC
  and embedded in the authenticated UI. You solve the challenge in the real
  page from whatever device you're on, press Resume, and the worker verifies
  the challenge is gone before continuing.
- **Extension executor:** with your explicit opt-in, the extension uses
  `chrome.debugger` (`Page.startScreencast` + `Input.dispatch*`) to stream that
  one tab to the container and relay *your* real taps and keystrokes back — a
  remote hand on the same mouse. The `debugger` permission is requested
  optionally, at first use, with a plain-English explanation. If you decline,
  or on Firefox where this isn't available, the job parks as
  *needs_human (at browser)* and waits for you.

The relay transports human input and generates none. There is no solving path
in the codebase.

---

## Configuration

Every variable is documented in [`.env.example`](.env.example). Highlights:

- `SECRET_KEY` (required), `ANTHROPIC_API_KEY` (optional; offline heuristics
  without it), `PORT=1456`.
- `MAX_APPLICATIONS_PER_HOUR` (15) / `MAX_APPLICATIONS_PER_DAY` (50) — enforced
  server-side.
- `MIN_HOST_INTERVAL_SECONDS` (1.0) — the polite floor; may only be raised.
- `INTERVENTION_WAIT_MINUTES` (30) — after which an unanswered job parks as
  *needs_human (waiting)* and the runner moves on; it never times out into an
  automatic attempt.
- Optional aggregator/search keys (Adzuna, Jooble, USAJobs, The Muse, Brave /
  SerpAPI) — absent keys disable that source gracefully; nothing falls back to
  scraping.

---

## Responsible use

JobPilot applies to jobs you actually want, with information you actually
provided. It respects rate limits and `robots.txt`, sends a truthful
identifying User-Agent, and does not scrape boards that forbid it (LinkedIn,
Indeed, Monster, Glassdoor, ZipRecruiter are permanent non-implementations —
see [`docs/SOURCES.md`](docs/SOURCES.md)). It hands every human-verification
challenge to a human. It never creates fake accounts, never auto-accepts terms
you haven't seen, never submits an application your run settings didn't
authorize, and applies at most once per posting. EEO/self-identification
answers default to *decline to self-identify* and are filled only as you
chose; a current-compensation field you left blank is left blank.

## Documentation

- [`CAPTCHA_POLICY.md`](CAPTCHA_POLICY.md) — the human-in-the-loop contract.
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — components and lifecycle.
- [`docs/SOURCES.md`](docs/SOURCES.md) — every connector and its permission basis.
- [`docs/PRIVACY.md`](docs/PRIVACY.md) — what stays local and what the LLM sees.
- [`docs/PLAN.md`](docs/PLAN.md) — the build plan and interpretation decisions.

## License

Provided as-is for personal, self-hosted use.
