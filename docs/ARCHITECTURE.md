# Architecture

JobPilot is one FastAPI origin (UI + REST + WebSocket on port 1456), a
background `arq` worker that drives the server-side Playwright executor,
Postgres, and Redis. A browser extension is the second, preferred executor —
it runs in your own browser with your own logged-in sessions. Both executors
share one resolver and one application state machine.

```
                            ┌──────────────────────────────────────────┐
   Browser (you)            │                 app  :1456               │
  ┌───────────────┐         │  FastAPI  ── REST /api/*                  │
  │  React SPA    │◀───────▶│           ── WebSocket /ws/ui, /ws/ext    │
  │  (served by   │  cookie │           ── static SPA + extension zips  │
  │   FastAPI)    │   + WS  │                                           │
  └───────────────┘         │   services/                              │
                            │     resolver ─ profile→custom→saved→LLM   │
  ┌───────────────┐  device │     search_service, ingest, intervention │
  │  Extension    │  token  │     pacing (throughput ceilings)          │
  │  (your        │◀───────▶│   sources/  polite HTTP, 12 connectors    │
  │   browser)    │  /ws/ext│   llm/      typed structured outputs      │
  │  content JS   │         │   executor/ state machine, captcha detect │
  └───────┬───────┘         └───────────────┬──────────────────────────┘
          │ fills the                       │ SQLAlchemy        Redis
          │ employer's                      ▼                   pub/sub
          │ real form              ┌─────────────┐  ┌─────────────────────┐
          ▼                        │  Postgres   │  │       worker        │
   employer ATS form               │  (your      │  │  arq queue runner   │
                                   │   volume)   │  │  Playwright Chromium │
                                   └─────────────┘  │  headful / Xvfb      │
                                                    │  + x11vnc + noVNC    │
                                                    └─────────────────────┘
```

## Request → application lifecycle

1. **Discover.** `search_service` runs the selected `sources/` connectors in a
   background thread with live per-source progress over `/ws/ui`. Web-search
   discovery (with the user's key) harvests ATS org slugs that feed the board
   connectors. Results are normalized, deduped (canonical URL + fuzzy
   title/company), salary-parsed, and enriched by one LLM pass (summary,
   requirements, education level, 0–100 match score).

2. **Queue.** The user picks listings and a mode (auto / review / draft) and an
   executor (extension / playwright / auto). `runs` creates one `Application`
   per listing — **one per posting, ever** — and transitions each to `queued`.

3. **Fill.** An executor claims a job:
   - *Extension:* the background service worker long-polls `/api/ext/next-job`,
     opens the apply page, and the content script discovers fields, asks the
     server-side `resolver` to resolve them, and fills them with humanized
     input.
   - *Playwright:* the worker's queue runner does the same with a headful
     Chromium page.
   Both share `services/resolver.py` and `executor/states.py`.

4. **Resolve.** For each field: structured profile (the 2026 field library) →
   custom fields → saved answers → LLM mapping → human. Hard rules:
   knockouts are never guessed, EEO comes only from explicit profile choices,
   blank current-compensation is never filled, unusual consent goes to a human,
   and long free-text drafts need one-time approval.

5. **Intervene.** Anything unresolved, any challenge, and (in review mode) the
   pre-submit gate becomes an `Intervention`. The user answers from the web UI
   (works on a phone); the answer optionally saves to the knowledge base and
   the executor resumes.

6. **Submit.** On success the executor captures a confirmation screenshot,
   snapshots every final field value, and writes the `application_events`
   audit trail. Ambiguous submits become `submitted_unconfirmed` — never a
   resubmission.

## The two invariants, in code

- **A human decides every CAPTCHA.** `executor/captcha.py` (server) and
  `extension/src/lib/challenge.ts` (client) *detect only*. On a match the
  executor halts all input, routes to a human (noVNC for Playwright; an
  opt-in `chrome.debugger` remote-hand relay for the extension), and
  re-verifies the challenge is gone before resuming. The architectural test
  `tests/test_captcha_policy.py` fails the build if any solver service,
  stealth/evasion tool, or challenge-directed OCR appears anywhere in the tree
  or the dependency manifests. See `CAPTCHA_POLICY.md`.

- **Answers are the user's own.** The resolver refuses to guess knockouts and
  the LLM context excludes EEO and current-compensation fields, so the model
  cannot leak them. See `services/resolver.py`.

## Storage & state

- Postgres holds every table in `backend/app/models/`. Migrations are Alembic;
  a test proves the migration chain builds exactly the model metadata.
- Redis backs the `arq` worker and the pub/sub relay that lets the worker push
  live events to UI WebSockets held by the app process.
- Uploads live on a named volume, scoped per user, served only after an auth +
  path-scoping check.

## Testing

126 backend tests cover connector parsing (recorded fixtures), politeness and
blocked handling, resolver precedence and the refuse-to-guess rules, the state
machine, cross-user isolation across every endpoint, the export/import
round-trip, the full extension flow (including a simulated CAPTCHA halting to a
human), and the CAPTCHA-solver ban. Frontend and extension both type-check and
build in CI.
