"""ATS board-API connectors: Greenhouse, Lever, Ashby, Workable,
SmartRecruiters, Recruitee.

All six publish official, keyless JSON endpoints that exist precisely so
that third parties can read public job boards. Each connector iterates the
user's discovered org slugs (see DiscoveredOrg; slugs are harvested by
search-engine discovery and manual adds) and filters client-side.
"""
from __future__ import annotations

from app.logging_conf import get_logger
from app.services.salary import parse_salary
from app.sources.base import JobSource, OrgRef, RawListing, SearchQuery, matches_query
from app.sources.http import PoliteHttpClient, SourceBlockedError
from app.sources.util import parse_iso, strip_html

log = get_logger(__name__)

# Per-search cap on orgs fetched per ATS so one search can't hammer a host.
MAX_ORGS_PER_SEARCH = 12


class BoardSource(JobSource):
    ats: str = ""

    def org_listings(
        self, org: OrgRef, http: PoliteHttpClient, query: SearchQuery
    ) -> list[RawListing]:  # pragma: no cover - abstract
        raise NotImplementedError

    def search(
        self, query: SearchQuery, http: PoliteHttpClient, orgs: list[OrgRef]
    ) -> list[RawListing]:
        results: list[RawListing] = []
        mine = [o for o in orgs if o.ats == self.ats][:MAX_ORGS_PER_SEARCH]
        for org in mine:
            try:
                listings = self.org_listings(org, http, query)
            except SourceBlockedError:
                raise
            except Exception as exc:
                log.warning("source.org_failed", source=self.name, slug=org.slug, error=str(exc))
                continue
            results.extend(li for li in listings if matches_query(li, query))
            if len(results) >= query.limit_per_source:
                break
        return results[: query.limit_per_source]


class GreenhouseSource(BoardSource):
    name = "greenhouse"
    label = "Greenhouse"
    ats = "greenhouse"
    permission_basis = (
        "Official public Job Board API (boards-api.greenhouse.io), documented by "
        "Greenhouse for retrieving published job posts."
    )

    def org_listings(self, org: OrgRef, http: PoliteHttpClient, query: SearchQuery) -> list[RawListing]:
        url = f"https://boards-api.greenhouse.io/v1/boards/{org.slug}/jobs"
        response = http.get(url, params={"content": "true"}, respect_robots=False)
        if response.status_code == 404:
            return []
        data = response.json()
        listings = []
        for job in data.get("jobs", []):
            content = strip_html(job.get("content"))
            salary = parse_salary(content[:2000] if content else None)
            listings.append(
                RawListing(
                    source=self.name,
                    external_id=str(job.get("id")),
                    url=job.get("absolute_url") or url,
                    apply_url=job.get("absolute_url"),
                    title=job.get("title", "Untitled"),
                    company=org.company_name or org.slug.capitalize(),
                    location=(job.get("location") or {}).get("name"),
                    posted_at=parse_iso(job.get("first_published") or job.get("updated_at")),
                    description=content,
                    salary_raw=salary.raw if salary.listed else None,
                    salary_min=salary.minimum,
                    salary_max=salary.maximum,
                    salary_currency=salary.currency,
                    salary_period=salary.period,
                    extra={"departments": [d.get("name") for d in job.get("departments", [])]},
                )
            )
        return listings


class LeverSource(BoardSource):
    name = "lever"
    label = "Lever"
    ats = "lever"
    permission_basis = (
        "Official public Postings API (api.lever.co/v0/postings), documented by "
        "Lever for reading published postings."
    )

    def org_listings(self, org: OrgRef, http: PoliteHttpClient, query: SearchQuery) -> list[RawListing]:
        url = f"https://api.lever.co/v0/postings/{org.slug}"
        response = http.get(url, params={"mode": "json"}, respect_robots=False)
        if response.status_code == 404:
            return []
        listings = []
        for job in response.json():
            categories = job.get("categories") or {}
            salary_range = job.get("salaryRange") or {}
            workplace = job.get("workplaceType")
            listings.append(
                RawListing(
                    source=self.name,
                    external_id=job.get("id"),
                    url=job.get("hostedUrl") or url,
                    apply_url=job.get("applyUrl") or job.get("hostedUrl"),
                    title=job.get("text", "Untitled"),
                    company=org.company_name or org.slug.capitalize(),
                    location=categories.get("location"),
                    remote=True if workplace == "remote" else (False if workplace == "on-site" else None),
                    posted_at=parse_iso(job.get("createdAt")),
                    description=job.get("descriptionPlain") or strip_html(job.get("description")),
                    salary_min=salary_range.get("min"),
                    salary_max=salary_range.get("max"),
                    salary_currency=salary_range.get("currency"),
                    salary_period=(salary_range.get("interval") or "").replace("-", "_") or None,
                    extra={"commitment": categories.get("commitment")},
                )
            )
        return listings


class AshbySource(BoardSource):
    name = "ashby"
    label = "Ashby"
    ats = "ashby"
    permission_basis = (
        "Official public Job Posting API (api.ashbyhq.com/posting-api), documented "
        "by Ashby for published job boards."
    )

    def org_listings(self, org: OrgRef, http: PoliteHttpClient, query: SearchQuery) -> list[RawListing]:
        url = f"https://api.ashbyhq.com/posting-api/job-board/{org.slug}"
        response = http.get(url, params={"includeCompensation": "true"}, respect_robots=False)
        if response.status_code == 404:
            return []
        data = response.json()
        listings = []
        for job in data.get("jobs", []):
            if job.get("isListed") is False:
                continue
            compensation = (job.get("compensation") or {}).get("compensationTierSummary")
            salary = parse_salary(compensation)
            listings.append(
                RawListing(
                    source=self.name,
                    external_id=job.get("id"),
                    url=job.get("jobUrl") or url,
                    apply_url=job.get("applyUrl") or job.get("jobUrl"),
                    title=job.get("title", "Untitled"),
                    company=org.company_name or org.slug.capitalize(),
                    location=job.get("location"),
                    remote=job.get("isRemote"),
                    posted_at=parse_iso(job.get("publishedAt")),
                    description=job.get("descriptionPlain") or strip_html(job.get("descriptionHtml")),
                    salary_raw=compensation,
                    salary_min=salary.minimum,
                    salary_max=salary.maximum,
                    salary_currency=salary.currency,
                    salary_period=salary.period,
                    extra={"department": job.get("department"), "team": job.get("team")},
                )
            )
        return listings


class WorkableSource(BoardSource):
    name = "workable"
    label = "Workable"
    ats = "workable"
    permission_basis = (
        "Official public widget API (apply.workable.com/api/v1/widget), provided by "
        "Workable for embedding published job boards."
    )

    def org_listings(self, org: OrgRef, http: PoliteHttpClient, query: SearchQuery) -> list[RawListing]:
        url = f"https://apply.workable.com/api/v1/widget/accounts/{org.slug}"
        response = http.get(url, params={"details": "true"}, respect_robots=False)
        if response.status_code == 404:
            return []
        data = response.json()
        company = data.get("name") or org.company_name or org.slug.capitalize()
        listings = []
        for job in data.get("jobs", []):
            location_bits = [job.get("city"), job.get("state"), job.get("country")]
            listings.append(
                RawListing(
                    source=self.name,
                    external_id=job.get("shortcode") or job.get("code"),
                    url=job.get("url") or job.get("shortlink") or url,
                    apply_url=job.get("application_url") or job.get("url"),
                    title=job.get("title", "Untitled"),
                    company=company,
                    location=", ".join(b for b in location_bits if b) or None,
                    remote=job.get("telecommuting"),
                    posted_at=parse_iso(job.get("published_on") or job.get("created_at")),
                    description=strip_html(job.get("description")),
                    education_level=(job.get("education") or "").lower() or None,
                    extra={"department": job.get("department")},
                )
            )
        return listings


class SmartRecruitersSource(BoardSource):
    name = "smartrecruiters"
    label = "SmartRecruiters"
    ats = "smartrecruiters"
    permission_basis = (
        "Official public Posting API (api.smartrecruiters.com/v1/companies/{company}/postings), "
        "documented by SmartRecruiters for published postings."
    )

    def org_listings(self, org: OrgRef, http: PoliteHttpClient, query: SearchQuery) -> list[RawListing]:
        url = f"https://api.smartrecruiters.com/v1/companies/{org.slug}/postings"
        response = http.get(url, respect_robots=False)
        if response.status_code == 404:
            return []
        data = response.json()
        listings = []
        for job in data.get("content", []):
            location = job.get("location") or {}
            location_bits = [location.get("city"), location.get("region"), location.get("country")]
            job_id = job.get("id")
            listings.append(
                RawListing(
                    source=self.name,
                    external_id=str(job_id),
                    url=f"https://jobs.smartrecruiters.com/{org.slug}/{job_id}",
                    apply_url=f"https://jobs.smartrecruiters.com/{org.slug}/{job_id}",
                    title=job.get("name", "Untitled"),
                    company=(job.get("company") or {}).get("name") or org.company_name or org.slug,
                    location=", ".join(b for b in location_bits if b) or None,
                    remote=location.get("remote"),
                    posted_at=parse_iso(job.get("releasedDate")),
                    description=None,  # list endpoint has no body; enrichment uses title/company
                    extra={"ref": job.get("refNumber")},
                )
            )
        return listings


class RecruiteeSource(BoardSource):
    name = "recruitee"
    label = "Recruitee"
    ats = "recruitee"
    permission_basis = (
        "Official public careers-site API ({org}.recruitee.com/api/offers), provided "
        "by Recruitee for published offers."
    )

    def org_listings(self, org: OrgRef, http: PoliteHttpClient, query: SearchQuery) -> list[RawListing]:
        url = f"https://{org.slug}.recruitee.com/api/offers/"
        response = http.get(url, respect_robots=False)
        if response.status_code == 404:
            return []
        data = response.json()
        listings = []
        for job in data.get("offers", []):
            listings.append(
                RawListing(
                    source=self.name,
                    external_id=str(job.get("id")),
                    url=job.get("careers_url") or url,
                    apply_url=job.get("careers_apply_url") or job.get("careers_url"),
                    title=job.get("title", "Untitled"),
                    company=org.company_name or org.slug.capitalize(),
                    location=job.get("location") or job.get("city"),
                    remote=job.get("remote"),
                    posted_at=parse_iso(job.get("published_at") or job.get("created_at")),
                    description=strip_html(job.get("description")),
                    extra={"department": job.get("department")},
                )
            )
        return listings
