"""Aggregator API connectors: Adzuna, Jooble, USAJobs, Remotive, Arbeitnow,
The Muse. All are official APIs; the keyed ones degrade gracefully to a
'disabled (no key)' state when unconfigured — nothing falls back to scraping.
"""
from __future__ import annotations

from app.config import get_settings
from app.logging_conf import get_logger
from app.services.salary import parse_salary
from app.sources.base import JobSource, OrgRef, RawListing, SearchQuery, matches_query
from app.sources.http import PoliteHttpClient
from app.sources.util import parse_iso, strip_html

log = get_logger(__name__)

# Rough country mapping for Adzuna's per-country endpoints.
ADZUNA_COUNTRIES = {
    "united states": "us", "usa": "us", "us": "us",
    "united kingdom": "gb", "uk": "gb", "great britain": "gb",
    "germany": "de", "france": "fr", "netherlands": "nl", "canada": "ca",
    "australia": "au", "austria": "at", "brazil": "br", "india": "in",
    "italy": "it", "mexico": "mx", "new zealand": "nz", "poland": "pl",
    "singapore": "sg", "south africa": "za", "spain": "es", "sweden": "se",
    "switzerland": "ch",
}


class AdzunaSource(JobSource):
    name = "adzuna"
    label = "Adzuna"
    permission_basis = "Official developer API (developer.adzuna.com) with the user's own app id/key."
    requires_key = True

    def is_configured(self) -> bool:
        s = get_settings()
        return bool(s.adzuna_app_id and s.adzuna_app_key)

    def search(self, query: SearchQuery, http: PoliteHttpClient, orgs: list[OrgRef]) -> list[RawListing]:
        s = get_settings()
        country = "us"
        if query.location:
            for name, code in ADZUNA_COUNTRIES.items():
                if name in query.location.lower():
                    country = code
                    break
        url = f"https://api.adzuna.com/v1/api/jobs/{country}/search/1"
        params = {
            "app_id": s.adzuna_app_id,
            "app_key": s.adzuna_app_key,
            "what": " ".join(query.terms)[:100],
            "results_per_page": min(query.limit_per_source, 50),
            "content-type": "application/json",
        }
        if query.location:
            params["where"] = query.location
        if query.salary_floor:
            params["salary_min"] = query.salary_floor
        if query.posted_within_days:
            params["max_days_old"] = query.posted_within_days
        response = http.get(url, params=params, respect_robots=False)
        results = []
        for job in response.json().get("results", []):
            results.append(
                RawListing(
                    source=self.name,
                    external_id=str(job.get("id")),
                    url=job.get("redirect_url", url),
                    apply_url=job.get("redirect_url"),
                    title=strip_html(job.get("title")) or "Untitled",
                    company=(job.get("company") or {}).get("display_name") or "Unknown",
                    location=(job.get("location") or {}).get("display_name"),
                    posted_at=parse_iso(job.get("created")),
                    description=strip_html(job.get("description")),
                    salary_min=int(job["salary_min"]) if job.get("salary_min") else None,
                    salary_max=int(job["salary_max"]) if job.get("salary_max") else None,
                    salary_currency="USD" if country == "us" else None,
                    salary_period="year",
                )
            )
        return results


class JoobleSource(JobSource):
    name = "jooble"
    label = "Jooble"
    permission_basis = "Official partner API (jooble.org/api/about) with the user's own key."
    requires_key = True

    def is_configured(self) -> bool:
        return bool(get_settings().jooble_api_key)

    def search(self, query: SearchQuery, http: PoliteHttpClient, orgs: list[OrgRef]) -> list[RawListing]:
        key = get_settings().jooble_api_key
        payload: dict = {"keywords": " ".join(query.terms)}
        if query.location:
            payload["location"] = query.location
        response = http.post_json(f"https://jooble.org/api/{key}", json=payload)
        results = []
        for job in response.json().get("jobs", [])[: query.limit_per_source]:
            salary = parse_salary(job.get("salary"))
            listing = RawListing(
                source=self.name,
                external_id=str(job.get("id")),
                url=job.get("link", "https://jooble.org"),
                apply_url=job.get("link"),
                title=job.get("title", "Untitled"),
                company=job.get("company") or "Unknown",
                location=job.get("location"),
                posted_at=parse_iso(job.get("updated")),
                description=strip_html(job.get("snippet")),
                salary_raw=job.get("salary") or None,
                salary_min=salary.minimum,
                salary_max=salary.maximum,
                salary_currency=salary.currency,
                salary_period=salary.period,
            )
            if matches_query(listing, query):
                results.append(listing)
        return results


class USAJobsSource(JobSource):
    name = "usajobs"
    label = "USAJobs"
    permission_basis = "Official US government API (developer.usajobs.gov) with the user's key + registered email."
    requires_key = True

    def is_configured(self) -> bool:
        s = get_settings()
        return bool(s.usajobs_api_key and s.usajobs_user_agent_email)

    def search(self, query: SearchQuery, http: PoliteHttpClient, orgs: list[OrgRef]) -> list[RawListing]:
        s = get_settings()
        params = {"Keyword": " ".join(query.terms), "ResultsPerPage": min(query.limit_per_source, 50)}
        if query.location:
            params["LocationName"] = query.location
        if query.salary_floor:
            params["RemunerationMinimumAmount"] = query.salary_floor
        response = http.get(
            "https://data.usajobs.gov/api/search",
            params=params,
            headers={
                "Authorization-Key": s.usajobs_api_key or "",
                # USAJobs documents that User-Agent must be the registered email.
                "User-Agent": s.usajobs_user_agent_email or "",
            },
            respect_robots=False,
        )
        results = []
        items = ((response.json().get("SearchResult") or {}).get("SearchResultItems")) or []
        for item in items:
            job = item.get("MatchedObjectDescriptor") or {}
            remuneration = (job.get("PositionRemuneration") or [{}])[0]
            interval = (remuneration.get("RateIntervalCode") or "").lower()
            period = {"pa": "year", "per year": "year", "ph": "hour", "per hour": "hour"}.get(
                interval, "year" if "year" in interval else None
            )
            details = (job.get("UserArea") or {}).get("Details") or {}
            results.append(
                RawListing(
                    source=self.name,
                    external_id=str(item.get("MatchedObjectId")),
                    url=job.get("PositionURI", "https://www.usajobs.gov"),
                    apply_url=(job.get("ApplyURI") or [job.get("PositionURI")])[0],
                    title=job.get("PositionTitle", "Untitled"),
                    company=job.get("OrganizationName") or "US Government",
                    location=job.get("PositionLocationDisplay"),
                    posted_at=parse_iso(job.get("PublicationStartDate")),
                    description=details.get("JobSummary"),
                    salary_min=int(float(remuneration.get("MinimumRange", 0))) or None,
                    salary_max=int(float(remuneration.get("MaximumRange", 0))) or None,
                    salary_currency="USD",
                    salary_period=period,
                )
            )
        return results


class RemotiveSource(JobSource):
    name = "remotive"
    label = "Remotive"
    permission_basis = "Official public API (remotive.com/api/remote-jobs), documented and keyless."

    def search(self, query: SearchQuery, http: PoliteHttpClient, orgs: list[OrgRef]) -> list[RawListing]:
        if query.remote is False:
            return []  # Remotive lists remote roles only.
        params = {"search": " ".join(query.terms)[:100], "limit": min(query.limit_per_source, 50)}
        response = http.get("https://remotive.com/api/remote-jobs", params=params, respect_robots=False)
        results = []
        for job in response.json().get("jobs", []):
            salary = parse_salary(job.get("salary"))
            listing = RawListing(
                source=self.name,
                external_id=str(job.get("id")),
                url=job.get("url", "https://remotive.com"),
                apply_url=job.get("url"),
                title=job.get("title", "Untitled"),
                company=job.get("company_name") or "Unknown",
                location=job.get("candidate_required_location"),
                remote=True,
                posted_at=parse_iso(job.get("publication_date")),
                description=strip_html(job.get("description")),
                salary_raw=job.get("salary") or None,
                salary_min=salary.minimum,
                salary_max=salary.maximum,
                salary_currency=salary.currency,
                salary_period=salary.period,
            )
            if matches_query(listing, query):
                results.append(listing)
        return results


class ArbeitnowSource(JobSource):
    name = "arbeitnow"
    label = "Arbeitnow"
    permission_basis = "Official public job-board API (arbeitnow.com/api/job-board-api), documented and keyless."

    def search(self, query: SearchQuery, http: PoliteHttpClient, orgs: list[OrgRef]) -> list[RawListing]:
        response = http.get("https://www.arbeitnow.com/api/job-board-api", respect_robots=False)
        results = []
        for job in response.json().get("data", []):
            listing = RawListing(
                source=self.name,
                external_id=job.get("slug"),
                url=job.get("url", "https://www.arbeitnow.com"),
                apply_url=job.get("url"),
                title=job.get("title", "Untitled"),
                company=job.get("company_name") or "Unknown",
                location=job.get("location"),
                remote=job.get("remote"),
                posted_at=parse_iso(job.get("created_at")),
                description=strip_html(job.get("description")),
            )
            if matches_query(listing, query):
                results.append(listing)
        return results[: query.limit_per_source]


class TheMuseSource(JobSource):
    name = "themuse"
    label = "The Muse"
    permission_basis = "Official public API (themuse.com/developers/api/v2); a key is optional and only raises rate limits."

    def search(self, query: SearchQuery, http: PoliteHttpClient, orgs: list[OrgRef]) -> list[RawListing]:
        params: dict = {"page": 1}
        key = get_settings().themuse_api_key
        if key:
            params["api_key"] = key
        if query.location:
            params["location"] = query.location
        response = http.get("https://www.themuse.com/api/public/jobs", params=params, respect_robots=False)
        results = []
        for job in response.json().get("results", []):
            locations = [loc.get("name") for loc in job.get("locations", [])]
            remote = any("flexible" in (loc or "").lower() or "remote" in (loc or "").lower() for loc in locations)
            listing = RawListing(
                source=self.name,
                external_id=str(job.get("id")),
                url=(job.get("refs") or {}).get("landing_page", "https://www.themuse.com"),
                apply_url=(job.get("refs") or {}).get("landing_page"),
                title=job.get("name", "Untitled"),
                company=(job.get("company") or {}).get("name") or "Unknown",
                location=", ".join(loc for loc in locations if loc) or None,
                remote=remote or None,
                posted_at=parse_iso(job.get("publication_date")),
                description=strip_html(job.get("contents")),
            )
            if matches_query(listing, query):
                results.append(listing)
        return results[: query.limit_per_source]
