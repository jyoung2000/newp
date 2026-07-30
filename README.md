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

## Install

### One command

Creates a `jobpilot/` folder, pulls the source from GitHub, generates a
`SECRET_KEY` and database password, and starts everything:

```bash
curl -fsSL https://raw.githubusercontent.com/jyoung2000/newp/refs/heads/claude/jobpilot-assistant-canrub/install.sh | bash
```

That URL names a branch, and it has to be a branch that exists —
`raw.githubusercontent.com` answers `404: Not Found` for one that doesn't,
rather than redirecting. `claude/jobpilot-assistant-canrub` is this
repository's default branch today; change that part of the URL if you are
tracking another one. Only fetching this script is affected — the installer
asks GitHub which branch to download.

Piping any script to `bash` deserves a look first — the safer form:

```bash
curl -fsSL https://raw.githubusercontent.com/jyoung2000/newp/refs/heads/claude/jobpilot-assistant-canrub/install.sh -o install.sh
less install.sh          # read it
bash install.sh
```

The installer never asks for your API key: set it in the UI at
**Settings → AI** once JobPilot is running (it is stored encrypted), or leave
it unset to run fully offline.

Options (environment variables):

| Variable | Default | Purpose |
|---|---|---|
| `JOBPILOT_DIR` | `./jobpilot` | Where to install |
| `JOBPILOT_PORT` | `1456` | Host port |
| `JOBPILOT_REF` | the repo's default branch | Branch or tag to install |
| `JOBPILOT_REPO` | `jyoung2000/newp` | Source repository |
| `JOBPILOT_NO_START` | – | Set to `1` to set up without starting |
| `JOBPILOT_DETACH` | – | Set to `1` to keep installing after you close the terminal |
| `JOBPILOT_LOG` | `<dir>.install.log` | Where the detached run writes its output |

```bash
# e.g. install to ~/apps/jobpilot on port 8080
JOBPILOT_DIR=~/apps/jobpilot JOBPILOT_PORT=8080 bash install.sh
```

`git` is used when present and skipped when it isn't — on a NAS without it,
the installer downloads a source archive instead.

### Installing over SSH, with the terminal closed

The first build takes several minutes, and closing an SSH session kills
whatever it was running. `JOBPILOT_DETACH=1` re-launches the installer in its
own session so a hangup can't reach it:

```bash
curl -fsSL https://raw.githubusercontent.com/jyoung2000/newp/refs/heads/claude/jobpilot-assistant-canrub/install.sh -o install.sh
JOBPILOT_DETACH=1 bash install.sh          # returns immediately
tail -f ./jobpilot.install.log             # watch it, or don't
```

It prints a pid and the log path, then returns — close the terminal whenever.
The run is finished when the log says `JobPilot is running` (or when
`curl -fsS http://localhost:1456/api/health` answers). This needs the script
on disk: a `curl … | bash` pipe has nothing to re-run, and the installer says
so rather than silently staying attached.

Re-running the installer updates the source in place and keeps your `.env`
and your data.

### Manual (git + docker compose)

```bash
mkdir -p ~/jobpilot && cd ~/jobpilot
git clone --depth 1 https://github.com/jyoung2000/newp.git .
cp .env.example .env
sed -i.bak "s|^SECRET_KEY=.*|SECRET_KEY=$(openssl rand -hex 32)|" .env && rm -f .env.bak
docker compose up -d --build
# → open http://localhost:1456
```

Setting `ANTHROPIC_API_KEY` in `.env` is optional — it is the fallback when a
user hasn't set their own key in Settings → AI. Without either, JobPilot uses
deterministic offline heuristics and sends nothing to Anthropic.

### Build the container and get the plugin out

The browser extension is compiled during the image build, so a normal build
already ships it — **Settings → Extension** offers both bundles for download.
If you would rather have the plugin as files on this machine (Chrome's *Load
unpacked* wants a folder, not a zip), build and unload it in one go:

```bash
# 1. build and start the stack (extension is built into the image)
docker compose up -d --build

# 2. copy the plugin out of the image into ./plugin
docker compose --profile plugin run --rm plugin
```

Or, from a clean folder, the whole thing as one command:

```bash
mkdir -p ~/jobpilot && cd ~/jobpilot \
  && git clone --depth 1 https://github.com/jyoung2000/newp.git . \
  && cp -n .env.example .env \
  && sed -i.bak "s|^SECRET_KEY=.*|SECRET_KEY=$(openssl rand -hex 32)|" .env && rm -f .env.bak \
  && docker compose up -d --build \
  && docker compose --profile plugin run --rm plugin
```

That leaves:

```
plugin/
├── chrome-unpacked/    → chrome://extensions → Developer mode → Load unpacked
├── firefox-unpacked/   → about:debugging → Load Temporary Add-on → manifest.json
├── jobpilot-chrome.zip
├── jobpilot-firefox.zip
└── VERSION
```

The `plugin` service is behind a compose profile, so it never starts with
`up`; it runs once, copies files out of the same `jobpilot-app:local` image the
server runs, and exits — so the extension you install always matches your
container. It needs no database, no Redis and no network access. Re-run it
after any rebuild to refresh the folder, then hit *Reload* on the extension in
your browser.

On Linux the container writes as root, so `./plugin` ends up root-owned
(harmless for loading it, annoying to delete). If that bothers you, or the
stack is already running and you don't want another container, copy it out
with the daemon instead — same files, owned by you:

```bash
mkdir -p plugin && docker compose cp app:/app/app/extension_dist/. ./plugin
```

### Updating

```bash
cd ~/jobpilot && ./update.sh
```

Keeps your `.env`, your database and your uploads. It fetches the latest code,
lists the commits you're about to run, rebuilds, and restarts — the web UI
first and on its own, then the executor, so a slow or failing worker build can
never take the UI down with it. Migrations apply themselves on boot.

| | |
|---|---|
| `./update.sh --check` | Say whether an update is available and stop. Doesn't need Docker running. |
| `./update.sh --no-worker` | Skip the executor rebuild (the big image). |
| `./update.sh --prune` | Delete the images this update orphaned, once it succeeds. |
| `make update` / `make update-check` | The same two, from the Makefile. |

It refuses to run over **local edits to tracked files**, listing them rather
than silently discarding them — `.env` is untracked and never at risk. If the
extension changed in the update it says so, since your copy of it needs
refreshing separately. On an install created from a source archive rather than
git there's no history to pull, and it tells you to re-run the installer, which
replaces the tree and keeps your `.env`.

### Everyday commands

```bash
./update.sh                  # update in place (see above)
docker compose logs -f app   # follow the app log
docker compose restart app   # after editing .env
docker compose down          # stop
docker compose down -v       # stop and DELETE all data (Postgres + uploads)
docker compose --profile plugin run --rm plugin  # refresh ./plugin after a rebuild
```

Compose builds four services — `app` (:1456), `worker`, `db` (Postgres 16),
`redis` (Redis 7) — with named volumes for Postgres, uploads, and the
Playwright browsers, plus the on-demand `plugin` service above. On first boot
the app applies migrations and seeds a demo user with live listings (falling
back to bundled fixtures if the boards are unreachable), so the UI isn't empty.
Everything waits on health, not on luck: `db` and `redis` must answer before
`app` starts, and the worker waits for `app` to report healthy — meaning
migrations are applied — before the queue runner touches a table.

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

## Settings

Everything configurable lives at **Settings** in the UI, in six sections:

| Section | What you set |
|---|---|
| **Security** | Password, TOTP two-factor (QR + verify), active sessions, revoke |
| **AI** | Anthropic API key, model, offline mode, test connection — see below |
| **Extension** | Download for Chrome/Firefox, load-unpacked walkthrough, 6-digit pairing code + QR, paired devices and revoke |
| **Preferences** | Default run mode and executor, "Type like a human" default, auto-answer confidence threshold, email/webhook notifications, timezone |
| **Data** | Export profile JSON / job lists CSV+JSON / application history CSV / everything as a zip; import profile with a merge preview, import job lists |
| **Danger zone** | Delete the account and all of its data |

## Accounts and the head admin

**The first account registered on an install becomes the head admin.** There is
no bootstrap password and nothing to set up: open the UI on a fresh install,
create your account, and it holds the role. Admins get a **Users** item in the
navigation that nobody else sees.

| Action | Where |
|---|---|
| See every account, its role, two-factor state and active sessions | Users |
| Create an account for someone (with a temporary password) | Users → Add an account |
| Grant or revoke administrator | Users → Make admin / Revoke admin |
| Reset a password without the old one (signs that account out everywhere) | Users → Reset password |
| Delete an account and everything in it | Users → Delete |

Two things this role deliberately does **not** do:

- **It does not open anyone else's job data.** Profiles, listings, runs and
  applications stay scoped to the user who owns them, enforced at the query
  layer and asserted by `tests/test_isolation.py`. Managing an account and
  reading its contents are different powers; only the first is granted.
- **It does not include the seeded demo account.** `demo@jobpilot.local` is
  created unattended with a password published in this file, so it never holds
  the role — and its existence doesn't stop the first real account from
  claiming it.

An install can't be left with no administrator: the last admin can't be demoted
or deleted while other accounts still exist. A one-person install is the
exception — deleting the only account is just leaving, and the next
registration takes the role again.

Upgrading an existing install promotes the earliest non-demo account, so
whoever set it up keeps managing it.

### Settings → AI

Your **Anthropic API key is set here**, not only in `.env`:

- It is **encrypted at rest** (AES-GCM with a key derived from `SECRET_KEY`)
  and **never shown again** — the UI displays only a hint like `sk-ant-…4f2a`.
- Precedence is **your key → `ANTHROPIC_API_KEY` → offline**. The UI states
  which one is in effect.
- **Model picker:** Claude Opus 5 (default, best parsing/mapping accuracy),
  Sonnet 5, Haiku 4.5, Opus 4.8.
- **Offline mode** turns off the LLM entirely — JobPilot falls back to
  deterministic local heuristics and sends nothing to Anthropic. Parsing and
  match scoring are rougher; everything else works the same.
- **Test connection** makes one tiny real call and reports the result (any
  error is scrubbed of the key before display).
- A "what the model sees" card lists the four AI tasks and states plainly
  that your EEO answers and current-compensation figure are never included.

## Your job list

Everything you collect — searched, captured or pasted — lands in one list you
can filter, sort, score against your profile and queue for auto-apply.

**Open application.** Every row carries a direct link beside the title (and the
detail drawer shows it as a full *Open application* button) that opens the
employer's own application page in a new tab — the listing's `apply_url`,
falling back to its canonical URL. It is a real anchor, so middle-click and
*Copy link address* behave, and clicking it doesn't open the row's drawer
underneath. It exists for the times you'd rather apply by hand: nothing is
queued and nothing is submitted, JobPilot just hands you the link.

---

## The browser extension

The extension is the default executor for anything interactive: it runs in
your own browser, so it uses your existing logged-in sessions and detection is
rarely an issue — the honest reason being that it *is* you.

### Install

Both bundles are built into the app and offered at **Settings → Extension**.
If you prefer files on disk over a browser download, `docker compose --profile
plugin run --rm plugin` writes them to `./plugin` (see
[Build the container and get the plugin out](#build-the-container-and-get-the-plugin-out)),
already unpacked — skip the "unzip it" step below and point *Load unpacked* at
`plugin/chrome-unpacked`.

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

### Linking — one code, copied from the browser

**Settings → Extension → Copy link code.** Paste it into the extension popup.
That's the whole flow — the popup has one field, and pasting a valid code links
immediately without hunting for a button.

The code is a single token that carries both halves of what pairing needs:

```
JP1-<base64url of {"u": "http://192.168.8.119:1456", "c": "418207"}>
```

The URL inside is the origin **your browser actually reached JobPilot on**, so
it is correct by construction. This matters more than it sounds: the old flow
asked for a server URL and a 6-digit code as separate fields, and the URL is
the half a person can't reasonably answer — `localhost` is right only when the
browser and the server are the same machine, which on a NAS they never are. Set
`PUBLIC_URL` and that wins instead, since it's the deliberate answer.

The base64 is not encryption and isn't meant to be; it exists so the thing is
one selectable token with no spaces or slashes to break a copy. The pairing
code inside is still single-use, short-lived and server-verified. Treat a link
code as carefully as the code it carries.

Prefer the old way? **Scan a QR code, or enter it by hand** under the code
reveals the QR, the 6 digits and the server URL, and the popup keeps manual
fields behind *Enter it manually instead* — useful when you're reading a code
off a phone screen.

The extension exchanges the code for a device token scoped to your account,
kept in `storage.local`. Devices are listed and revocable in Settings; the
popup and the container both show link status.

### Autofill — one click, or one keystroke

On any application form:

- **Extension popup → Fill this form**, or
- **Alt+Shift+F** (a suggestion — rebind it at `chrome://extensions/shortcuts`,
  or Firefox's *Manage Extension Shortcuts*; the popup shows your actual
  binding, and says so when none is set)

Values come from what **you** entered in JobPilot — profile, custom fields,
saved answers — resolved by the same server-side resolver the queued runs use,
so knockout questions and EEO fields are handled identically. No application,
no run and no saved listing are involved; it works on any form you're looking
at.

Two rules it will not bend:

- **It never submits.** It fills, highlights, reports what it did, and stops.
  You press the button.
- **A CAPTCHA or verification step halts it** before anything is typed. If one
  appears mid-fill, it stops there and leaves what's already entered for you to
  check. Software never answers a challenge — see
  [docs/CAPTCHA.md](docs/CAPTCHA.md).

Anything the resolver isn't confident about is left **empty and highlighted**
rather than guessed at. A wrong answer on an application is worse than a blank
one you notice.

#### How it decides what goes where

In order, stopping at the first that works:

1. **The DOM's own labelling** — `aria-label`, `aria-labelledby`,
   `<label for=…>`, a wrapping `<label>`, a `<fieldset>` legend, then the
   `placeholder`.
2. **The `name` attribute**, plus the surrounding text of the field's container
   for context.
3. **Reading the pixels** — last resort, for a field with none of the above: a
   canvas-drawn form, or a control labelled only by an image. The extension
   crops the screenshot to that one field and asks your configured model to
   read the label.

Step 3 is bounded on purpose. It runs only for fields that produced nothing
from steps 1–2, it sends a crop of a single field rather than the page, and
**in offline mode it doesn't run at all** — the field goes to you instead,
which is the same answer JobPilot gives for anything else it can't determine.

### "Save this job" — capturing the page you're on

Plenty of good postings live on boards JobPilot will never fetch (LinkedIn,
Indeed, Monster, Glassdoor, ZipRecruiter — see
[`docs/SOURCES.md`](docs/SOURCES.md)). You can still browse those sites
yourself, and keep what you find:

1. **You** open the job page, in your own browser, the normal way.
2. Click the JobPilot extension and press **Save this job**.
3. The extension reads the posting out of the tab you're looking at — title,
   company, location, description, salary text, apply link, post date — and
   sends it to your container over the paired device token.
4. It shows up in your job list, parsed for salary and dates, summarized and
   match-scored like any other listing. Saving the same posting twice (or the
   same URL with different tracking parameters) returns the row you already
   have instead of duplicating it.

**This is not scraping.** You navigated to the page; the content comes from
your browser, and **the server never sends a request to that site** — not at
save time, not later (`captured` is not a fetchable source), which is exactly
why this is allowed to work on sites JobPilot itself must not fetch. The button
saves **one page per click, the one you are on**. There is no crawling, no list
of URLs, no background pass, and no change to the rule that JobPilot does not
scrape those boards.

To be exact about what *does* leave your container: if you have an AI key
configured, a captured listing is summarized and match-scored through your
configured model, the same as every other listing — one call to your own model
provider. Turn AI off in Settings → AI and capture stores the page with no
outbound call at all. Either way, nothing is ever requested from the job board.

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

- `SECRET_KEY` — set it yourself, or let the containers generate one into the
  uploads volume on first boot (they share it; deleting it logs everyone out
  and orphans stored API keys). `ANTHROPIC_API_KEY` is optional — offline
  heuristics without it, or set it per user in Settings → AI. `PORT=1456`.
- **`.env` itself is optional.** Every value has a working default; the file
  only exists so you can change them.
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
see [`docs/SOURCES.md`](docs/SOURCES.md); you can still save a posting you are
personally reading there with **Save this job**). It hands every
human-verification challenge to a human. It never creates fake accounts, never
auto-accepts terms you haven't seen, never submits an application your run
settings didn't authorize, and applies at most once per posting.
EEO/self-identification answers default to *decline to self-identify* and are
filled only as you chose; a current-compensation field you left blank is left
blank.

## Documentation

- [`CAPTCHA_POLICY.md`](CAPTCHA_POLICY.md) — the human-in-the-loop contract.
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — components and lifecycle.
- [`docs/SOURCES.md`](docs/SOURCES.md) — every connector and its permission basis.
- [`docs/PRIVACY.md`](docs/PRIVACY.md) — what stays local and what the LLM sees.
- [`docs/UNRAID.md`](docs/UNRAID.md) — running it under Unraid's Compose Manager.
- [`docs/PLAN.md`](docs/PLAN.md) — the build plan and interpretation decisions.

## License

Provided as-is for personal, self-hosted use.
