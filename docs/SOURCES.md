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
| **Capture from your own browsing (extension)** | User-initiated save of the page in front of them | No | The user navigates to the job page themselves and clicks *Save this job*. JobPilot performs no automated collection, sends no request to that site, and stores only what the user was already looking at. |

### Capture from your own browsing

This is a person reading a job posting and pressing a button, so it is worth
being exact about what it is and is not:

- The **user** opens the page. Nothing in JobPilot navigates, crawls, follows
  links, or schedules a fetch.
- The page content is read out of the **tab the user is on**, by the extension
  running in the user's own browser, and posted to the user's own JobPilot
  container over the paired device token. **The server never sends a request to
  the captured site** — not when saving, and not afterwards: `captured` is not
  a fetchable source, so nothing can re-fetch the page later either. This is
  the guarantee capture rests on, and `backend/tests/test_capture.py` asserts
  it against real outbound traffic.
- It is not, however, an endpoint with no network at all: with an AI key
  configured, a captured listing is summarized and match-scored through the
  user's own configured model, exactly like every other listing. That is one
  call to their model provider (none at all with AI off) — never to the board.
- It saves **one page per click**: the one on screen. There is no "capture all
  results", no queue of URLs, no background pass.
- What is stored is what the user was already looking at (title, company,
  location, description, salary text, apply link, post date), normalized and
  deduplicated like any other listing, and it lands in that user's list only.

## Forbidden sources (deliberate, permanent stubs)

These boards prohibit automated collection in their terms of service and
actively defend against it. JobPilot ships them as `NotImplementedSource`
stubs that raise with a stated reason and are surfaced in the UI as
`forbidden`. **They are not implemented, and will not be added later behind a
flag** — JobPilot will not fetch a single page from them.

That is a limit on the software, not on you. These boards remain usable, by
two routes:

1. **Browse them yourself and save what you find.** Open a posting the normal
   way, in your own browser, and click the extension's *Save this job* button
   (or paste the listing via *Add listing manually*). The posting joins your
   list with search, scoring, tracking and apply like any other — one page per
   click, the one you are on. JobPilot still sends no request of its own to
   these sites; the content comes from the tab you already opened.
2. **Their own official API, with your own credentials.** Where one of these
   companies runs a partner/publisher API and you hold an agreement for it,
   that API — not scraping — is the legitimate automated route. JobPilot ships
   no connector for these particular APIs; adding one would mean your own
   credentials, the way Adzuna, Jooble and USAJobs already work.

| Source | Why not | What works instead |
|---|---|---|
| **LinkedIn** | The LinkedIn User Agreement prohibits automated access/scraping. | Browse it yourself and *Save this job*; or LinkedIn's official partner API with your own credentials. |
| **Indeed** | Indeed's terms of service prohibit scraping; its publisher API is invite-only. | Browse it yourself and *Save this job*; or Indeed's publisher API if you have been granted access. |
| **Monster** | Monster's terms of use prohibit automated collection. | Browse it yourself and *Save this job*; or Monster's partner API with your own credentials. |
| **Glassdoor** | Glassdoor's terms of use prohibit scraping. | Browse it yourself and *Save this job*; or Glassdoor's partner API with your own credentials. |
| **ZipRecruiter** | ZipRecruiter's terms prohibit automated access without a partner agreement. | Browse it yourself and *Save this job*; or its partner API under an agreement you hold. |

## Applying

Applications go to the **employer's own application form** (their ATS), which
exists precisely to receive them — permitted use. JobPilot enforces a
configurable throughput ceiling (default **15 applications/hour**, **50/day**)
server-side in the queue runner and at every submission entry point, applies
at most **one application per posting, ever** (hard dedupe), and never submits
an application the user's run settings didn't authorize.
