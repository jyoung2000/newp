# Privacy

JobPilot is **single-tenant and self-hosted by default**. You run it on your
own machine or server; your data lives in your own Postgres volume and your
own uploads volume. There is **no telemetry, no phone-home, and no
third-party analytics** anywhere in this project.

## What stays on your machine

Everything, except the two outbound categories below:

- Your profile, work history, education, recommendations, custom fields, and
  saved answers — in your Postgres volume.
- Uploaded files (resumes, cover letters, certifications, portfolio items,
  and confirmation/intervention screenshots) — on a local uploads volume,
  scoped per user, and never served without an authenticated ownership check
  (`backend/app/services/storage.py`, `backend/app/api/files.py`).
- Application field snapshots and the audit trail of every application.

## What leaves your machine, and to whom

**1. Job sources you query.** When you run a search, JobPilot fetches from the
job-source APIs listed in `SOURCES.md` using a truthful, identifying
User-Agent. These requests contain your search terms and location, not your
profile. Aggregators that need a key use *your* key.

**2. The Anthropic API (the LLM).** JobPilot uses the Anthropic API for a
small set of tasks, and this is the one place your data is sent to a
third party. Specifically, the model sees:

- **Résumé text**, when you ask JobPilot to parse your default résumé into
  structured fields (you review and confirm the parse before it is used).
- **Job-listing text and a compact summary of your profile**, when scoring
  how well a listing matches you (the summary is the "key: value" context
  built in `resolver.build_llm_context`).
- **A single form field's label, type, options and surrounding text, plus
  that same profile context**, when mapping an unrecognized field to your
  stored data.
- **A question and your own facts**, when drafting a free-text answer.

The profile context sent to the model is built to **exclude your EEO
self-identification answers and your current-compensation figure** — those
are never placed in the LLM context, so they cannot leak into a generated
answer. The model is instructed, in every prompt, to answer only from the
facts you provided and to return "unknown" rather than invent anything.

If you set `LLM_DRY_RUN=1` (or simply provide no `ANTHROPIC_API_KEY`),
JobPilot uses deterministic offline heuristics for all of the above and
**sends nothing to Anthropic** — useful for evaluating the tool privately,
at some cost to parse/mapping quality.

Review Anthropic's data-usage terms for your account. JobPilot does not train
anything, store your data remotely, or send it anywhere other than the two
categories above.

## Remote access

If you expose the UI beyond `localhost` (set `PUBLIC_URL`), turn on TOTP 2FA
and put it behind a reverse proxy or a tailnet — see the README's
"Remote access" section. Secure cookies and HSTS switch on automatically when
`PUBLIC_URL` is an `https://` origin. The noVNC viewer used for remote CAPTCHA
solving is bound to `127.0.0.1` by default and embedded only inside the
authenticated UI.

## Deleting your data

Settings → Delete account cascades every database row belonging to you and
removes your uploads directory. You can also export everything first
(Settings → Export, or the `/api/transfer/*` endpoints) as JSON/CSV plus a
zip of your files.
