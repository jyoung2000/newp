"""Search-engine discovery of ATS-hosted listings — the engine behind
"search the internet".

Runs site-scoped queries (site:boards.greenhouse.io "{title}" {location}, …)
through an official search API the user holds a key for (Brave Search or
SerpAPI). Result URLs surface listings directly (via the ATS org slug they
reveal) and grow the per-user DiscoveredOrg table that feeds the board
connectors. Without a key the source reports disabled — JobPilot never
scrapes a search engine's HTML.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from app.config import get_settings
from app.logging_conf import get_logger
from app.sources.base import JobSource, OrgRef, RawListing, SearchQuery
from app.sources.http import PoliteHttpClient

log = get_logger(__name__)

ATS_SITES = [
    "boards.greenhouse.io",
    "jobs.lever.co",
    "jobs.ashbyhq.com",
    "apply.workable.com",
    "jobs.smartrecruiters.com",
]

# URL shapes that reveal an org slug per ATS.
SLUG_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("greenhouse", re.compile(r"boards\.greenhouse\.io/(?:embed/job_board\?for=)?([a-z0-9_-]+)", re.I)),
    ("greenhouse", re.compile(r"job-boards\.greenhouse\.io/([a-z0-9_-]+)", re.I)),
    ("lever", re.compile(r"jobs\.lever\.co/([a-z0-9_-]+)", re.I)),
    ("ashby", re.compile(r"jobs\.ashbyhq\.com/([a-z0-9_%-]+)", re.I)),
    ("workable", re.compile(r"apply\.workable\.com/(?!api/)([a-z0-9_-]+)", re.I)),
    ("smartrecruiters", re.compile(r"jobs\.smartrecruiters\.com/([A-Za-z0-9_-]+)", re.I)),
    ("recruitee", re.compile(r"https?://([a-z0-9-]+)\.recruitee\.com", re.I)),
]

IGNORED_SLUGS = {"jobs", "job", "www", "embed", "search", "api", "careers"}


@dataclass
class WebSearchResult:
    url: str
    title: str
    snippet: str


def harvest_org_refs(urls: list[str]) -> list[OrgRef]:
    seen: set[tuple[str, str]] = set()
    refs: list[OrgRef] = []
    for url in urls:
        for ats, pattern in SLUG_PATTERNS:
            m = pattern.search(url)
            if not m:
                continue
            slug = m.group(1).lower().strip("/")
            if not slug or slug in IGNORED_SLUGS or (ats, slug) in seen:
                continue
            seen.add((ats, slug))
            refs.append(OrgRef(ats=ats, slug=slug))
    return refs


class WebSearchDiscovery(JobSource):
    name = "websearch"
    label = "Web search discovery"
    permission_basis = (
        "Site-scoped queries via the official Brave Search API or SerpAPI using the "
        "user's own key. JobPilot never scrapes search-engine result pages."
    )
    requires_key = True

    def is_configured(self) -> bool:
        s = get_settings()
        return bool(s.brave_search_api_key or s.serpapi_api_key)

    def run_queries(self, query: SearchQuery, http: PoliteHttpClient) -> list[WebSearchResult]:
        results: list[WebSearchResult] = []
        location = query.location or ""
        for site in ATS_SITES:
            for term in query.terms[:3]:
                q = f'site:{site} "{term}" {location}'.strip()
                results.extend(self._one_query(q, http))
        return results

    def _one_query(self, q: str, http: PoliteHttpClient) -> list[WebSearchResult]:
        s = get_settings()
        try:
            if s.brave_search_api_key:
                response = http.get(
                    "https://api.search.brave.com/res/v1/web/search",
                    params={"q": q, "count": 10},
                    headers={
                        "X-Subscription-Token": s.brave_search_api_key,
                        "Accept": "application/json",
                    },
                    respect_robots=False,
                )
                items = ((response.json().get("web") or {}).get("results")) or []
                return [
                    WebSearchResult(
                        url=i.get("url", ""), title=i.get("title", ""), snippet=i.get("description", "")
                    )
                    for i in items
                ]
            if s.serpapi_api_key:
                response = http.get(
                    "https://serpapi.com/search.json",
                    params={"q": q, "api_key": s.serpapi_api_key, "num": 10},
                    respect_robots=False,
                )
                items = response.json().get("organic_results") or []
                return [
                    WebSearchResult(
                        url=i.get("link", ""), title=i.get("title", ""), snippet=i.get("snippet", "")
                    )
                    for i in items
                ]
        except Exception as exc:
            log.warning("websearch.query_failed", q=q, error=str(exc))
        return []

    def search(self, query: SearchQuery, http: PoliteHttpClient, orgs: list[OrgRef]) -> list[RawListing]:
        """Discovery yields org slugs rather than listings; the search runner
        feeds harvested slugs to the board connectors in the same run."""
        return []
