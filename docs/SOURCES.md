# Job sources and their permission basis

Every source JobPilot fetches from is listed here with the specific basis on
which fetching is permitted. The boards that forbid automated collection are
shipped as permanent, deliberate stubs — see the bottom of this table.

The politeness guarantees below are enforced in code, not just documented:
`backend/app/sources/http.py` sends a truthful identifying User-Agent, caches
and respects `robots.txt` per host, holds a hard floor of **1 request per
second per host** (configuration can only make it slower — the app refuses to
start otherwise, see `Settings.validate_politeness`), backs off on transient
errors, and marks a source `blocked` — never retried with evasion — on any
401 / 403 / 429 or bot-block interstitial.

## Permitted sources

| Source | Type | Key required | Permission basis |
|---|---|---|---|
| **Greenhouse** | ATS board API | No | Official public Job Board API `boards-api.greenhouse.io/v1/boards/{org}/jobs?content=true`, published by Greenhouse for reading public job boards. |
| **Lever** | ATS board API | No | Official public Postings API `api.lever.co/v0/postings/{org}?mode=json`, published by Lever for reading published postings. |
| **Ashby** | ATS board API | No | Official public Job Posting API `api.ashbyhq.com/posting-api/job-board/{org}`, published by Ashby. |
| **Workable** | ATS board API | No | Official public widget API `apply.workable.com/api/v1/widget/accounts/{org}`, provided by Workable to embed public boards. |
| **SmartRecruiters** | ATS board API | No | Official public Posting API `api.smartrecruiters.com/v1/companies/{company}/postings`. |
| **Recruitee** | ATS board API | No | Official public careers-site API `{org}.recruitee.com/api/offers/`. |
| **Adzuna** | Aggregator API | Yes (app id + key) | Official developer API, `developer.adzuna.com`, used with the user's own credentials. |
| **Jooble** | Aggregator API | Yes | Official partner API, `jooble.org/api`, used with the user's own key. |
| **USAJobs** | Government API | Yes (key + email) | Official US government API, `developer.usajobs.gov`; User-Agent must be the registered email, which the app sends. |
| **Remotive** | Aggregator API | No | Official public API `remotive.com/api/remote-jobs`, documented and keyless. |
| **Arbeitnow** | Aggregator API | No | Official public job-board API `arbeitnow.com/api/job-board-api`, documented and keyless. |
| **The Muse** | Aggregator API | Optional | Official public API `themuse.com/api/public/jobs`; a key is optional and only raises rate limits. |
| **JSON-LD (`schema.org/JobPosting`)** | Structured data on public careers pages | No | The same structured data employers deliberately publish for search engines to index. Fetched robots-permitting, via the polite client. |
| **Web-search discovery** | Site-scoped queries against ATS domains | Yes (Brave or SerpAPI key) | Uses the user's own Brave Search API or SerpAPI key to find ATS-hosted listing URLs and harvest org slugs. JobPilot never scrapes a search engine's result pages; without a key the source reports `disabled`. |
| **Manual add** | User-pasted URL or listing | No | The user found the listing themselves; JobPilot parses what's public at the URL (robots-permitting) or stores exactly what the user pasted. |

## Forbidden sources (deliberate, permanent stubs)

These boards prohibit automated collection in their terms of service and
actively defend against it. JobPilot ships them as `NotImplementedSource`
stubs that raise with a stated reason and are surfaced in the UI as
`forbidden`. **They are not implemented, and will not be added later behind a
flag.** The honest path is to browse them normally and paste anything you find
via *Add listing manually*.

| Source | Why not |
|---|---|
| **LinkedIn** | The LinkedIn User Agreement prohibits automated access/scraping. |
| **Indeed** | Indeed's terms of service prohibit scraping; its publisher API is invite-only. |
| **Monster** | Monster's terms of use prohibit automated collection. |
| **Glassdoor** | Glassdoor's terms of use prohibit scraping. |
| **ZipRecruiter** | ZipRecruiter's terms prohibit automated access without a partner agreement. |

## Applying

Applications go to the **employer's own application form** (their ATS), which
exists precisely to receive them — permitted use. JobPilot enforces a
configurable throughput ceiling (default **15 applications/hour**, **50/day**)
server-side in the queue runner and at every submission entry point, applies
at most **one application per posting, ever** (hard dedupe), and never submits
an application the user's run settings didn't authorize.
