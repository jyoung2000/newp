# JobPilot build plan

This file records the phase plan and the interpretation decisions made while
building JobPilot from the one-shot specification. The build ran autonomously,
so ambiguities were resolved with the most conservative reading and recorded
here instead of blocking on questions.

## Phases

1. **Scaffold** — repo layout, `pyproject.toml`, Docker compose, CI, env
   examples, Makefile, the CAPTCHA-policy architectural test (written first so
   every later phase is checked against it).
2. **Auth & isolation** — argon2id accounts, opaque session cookies, CSRF,
   login rate limiting, optional TOTP, sessions/devices tables, cross-user
   isolation enforcement + tests.
3. **Profile & field library** — profile tabs data model, work experience,
   education, recommendations, files (upload/scoped serving/default resume),
   custom fields, saved answers, the 2026 canonical field library.
4. **Discovery** — polite HTTP layer (robots.txt, truthful UA, 1 req/s/host,
   backoff, blocked states), ATS board connectors (Greenhouse, Lever, Ashby,
   Workable, SmartRecruiters, Recruitee), aggregators (Adzuna, Jooble,
   USAJobs, Remotive, Arbeitnow, The Muse), JSON-LD extraction, search-engine
   discovery (Brave/SerpAPI), forbidden-source stubs, manual add,
   normalization/dedupe/salary parsing, LLM enrichment.
5. **Resolver & knowledge base** — resolution precedence (profile → custom
   fields → saved answers → LLM), knockout refusal-to-guess, EEO rules,
   consent rules, free-text draft approval flow.
6. **Executor & state machine** — application state machine with audit
   events, CAPTCHA/challenge detection, humanized input, Playwright executor,
   queue runner with server-side throughput ceilings.
7. **Extension** — wxt source tree (Chrome MV3 + Firefox), pairing, WS
   protocol, content-script field detection + fill engine, popup, opt-in
   `chrome.debugger` relay for remote CAPTCHA solving.
8. **Interventions** — unknown-field answer flow (local + remote), challenge
   flow, review mode, notifications (WS, badge, email, webhook).
9. **Analytics & transfer** — dashboard, application log/timeline, outcomes,
   funnel, export/import with lossless round-trip.
10. **Frontend** — React 18 + Vite + TS + Tailwind, typed client generated
    from OpenAPI, Apple-like design system, responsive down to phone width.
11. **Docs & polish** — README, ARCHITECTURE, CAPTCHA_POLICY, SOURCES,
    PRIVACY, seed script.

## Interpretation decisions

- **Python version**: the build environment provides CPython 3.12 via `uv`;
  Docker images use `python:3.12-slim`. Code targets 3.12.
- **Tests vs Postgres**: production runs Postgres 16 (compose). The test
  suite runs against SQLite with portable column types (JSON, DateTime,
  String enums) so `make test` needs no services. The Alembic migration is
  generated from the same metadata and applies to both.
- **Build-environment network**: the sandbox in which this repo was built
  allows package registries but blocks general HTTPS, so live-listing seeding
  and real-board integration tests could not be executed here. Connector
  tests run against recorded fixtures; the seed script tries live boards
  first and falls back to bundled fixtures, stating which it used.
- **`needs_human (waiting)`** is modeled as status `needs_human` plus a
  `parked_at` timestamp set when the response window lapses; the runner never
  blocks on a parked job and never times out into an automatic attempt.
- **Current compensation**: left blank in the profile ⇒ the resolver returns
  a `leave_blank` action for optional fields and raises an intervention when
  the form marks it required. It is never inferred.
- **Free-text drafts**: an LLM draft longer than the trivial-length threshold
  (120 chars) is stored unapproved; in auto mode it becomes a review
  intervention until the user approves it once for that job family, after
  which it is reusable.
- **noVNC**: the worker container ships Xvfb + x11vnc + websockify and the UI
  embeds the viewer through the authenticated app; this could not be executed
  in the build sandbox (no Docker daemon) and is marked as such in the README.
- **Search-engine discovery** requires a user-supplied Brave or SerpAPI key;
  without one the source reports `disabled (no key)` rather than scraping a
  search engine HTML page, which their terms forbid.
