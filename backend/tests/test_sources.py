from __future__ import annotations

import json
from pathlib import Path

import pytest
import respx
from httpx import Response

from app.sources.aggregators import ArbeitnowSource, RemotiveSource, TheMuseSource
from app.sources.ats_boards import (
    AshbySource,
    GreenhouseSource,
    LeverSource,
    RecruiteeSource,
    SmartRecruitersSource,
    WorkableSource,
)
from app.sources.base import ForbiddenSourceError, OrgRef, SearchQuery
from app.sources.forbidden import IndeedSource, LinkedInSource
from app.sources.http import PoliteHttpClient, SourceBlockedError
from app.sources.jsonld import extract_jobpostings_from_html
from app.sources.websearch import harvest_org_refs

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture()
def http(engine):
    client = PoliteHttpClient()
    client.min_interval = 0.0  # politeness pacing tested separately
    return client


def _fixture(name: str):
    return json.loads((FIXTURES / name).read_text())


QUERY = SearchQuery(terms=["python", "engineer", "designer", "developer", "reliability", "frontend", "machine"])


@respx.mock
def test_greenhouse_parsing(http):
    respx.get("https://boards-api.greenhouse.io/v1/boards/acmecorp/jobs").mock(
        return_value=Response(200, json=_fixture("greenhouse_jobs.json"))
    )
    listings = GreenhouseSource().org_listings(OrgRef("greenhouse", "acmecorp", "Acme Corp"), http, QUERY)
    assert len(listings) == 2
    first = listings[0]
    assert first.title == "Senior Backend Engineer"
    assert first.company == "Acme Corp"
    assert "Python" in (first.description or "")
    assert "<" not in (first.description or "")  # HTML stripped
    assert first.salary_min == 150000 and first.salary_max == 180000
    assert first.salary_currency == "USD" and first.salary_period == "year"
    assert first.posted_at is not None


@respx.mock
def test_lever_parsing(http):
    respx.get("https://api.lever.co/v0/postings/globex").mock(
        return_value=Response(200, json=_fixture("lever_postings.json"))
    )
    listings = LeverSource().org_listings(OrgRef("lever", "globex"), http, QUERY)
    assert len(listings) == 2
    payments = listings[0]
    assert payments.salary_min == 85000 and payments.salary_currency == "GBP"
    assert payments.remote is None  # hybrid -> neither strictly remote nor onsite
    assert listings[1].remote is True


@respx.mock
def test_ashby_skips_unlisted(http):
    respx.get("https://api.ashbyhq.com/posting-api/job-board/initech").mock(
        return_value=Response(200, json=_fixture("ashby_board.json"))
    )
    listings = AshbySource().org_listings(OrgRef("ashby", "initech"), http, QUERY)
    assert len(listings) == 1
    assert listings[0].title == "Machine Learning Engineer"
    assert listings[0].salary_min == 185000 and listings[0].salary_max == 230000


@respx.mock
def test_workable_parsing(http):
    respx.get("https://apply.workable.com/api/v1/widget/accounts/hooli").mock(
        return_value=Response(200, json=_fixture("workable_widget.json"))
    )
    listings = WorkableSource().org_listings(OrgRef("workable", "hooli"), http, QUERY)
    assert len(listings) == 1
    job = listings[0]
    assert job.company == "Hooli"
    assert job.remote is True
    assert job.location == "Berlin, Berlin, Germany"
    assert job.education_level == "bachelor's degree"


@respx.mock
def test_smartrecruiters_parsing(http):
    respx.get("https://api.smartrecruiters.com/v1/companies/PiedPiper/postings").mock(
        return_value=Response(200, json=_fixture("smartrecruiters_postings.json"))
    )
    listings = SmartRecruitersSource().org_listings(OrgRef("smartrecruiters", "PiedPiper"), http, QUERY)
    assert len(listings) == 1
    assert listings[0].company == "Pied Piper"
    assert "smartrecruiters.com/PiedPiper/744000060001" in listings[0].url


@respx.mock
def test_recruitee_parsing(http):
    respx.get("https://vandelay.recruitee.com/api/offers/").mock(
        return_value=Response(200, json=_fixture("recruitee_offers.json"))
    )
    listings = RecruiteeSource().org_listings(OrgRef("recruitee", "vandelay"), http, QUERY)
    assert len(listings) == 1
    assert listings[0].remote is True
    assert listings[0].title == "Python Developer"


@respx.mock
def test_remotive_and_arbeitnow_and_themuse(http):
    respx.get("https://remotive.com/api/remote-jobs").mock(
        return_value=Response(200, json=_fixture("remotive.json"))
    )
    respx.get("https://www.arbeitnow.com/api/job-board-api").mock(
        return_value=Response(200, json=_fixture("arbeitnow.json"))
    )
    respx.get("https://www.themuse.com/api/public/jobs").mock(
        return_value=Response(200, json=_fixture("themuse.json"))
    )
    query = SearchQuery(terms=["python"])
    remotive = RemotiveSource().search(query, http, [])
    assert len(remotive) == 1 and remotive[0].remote is True
    assert remotive[0].salary_min == 90000

    arbeitnow = ArbeitnowSource().search(query, http, [])
    # Marketing role filtered out by the query terms.
    assert [li.title for li in arbeitnow] == ["Python Backend Developer"]

    muse = TheMuseSource().search(query, http, [])
    assert len(muse) == 1 and muse[0].company == "Dunder Mifflin Digital"


@respx.mock
def test_blocked_status_raises_and_never_retries(http):
    route = respx.get("https://api.lever.co/v0/postings/blockedco").mock(
        return_value=Response(403, text="Forbidden")
    )
    with pytest.raises(SourceBlockedError):
        LeverSource().org_listings(OrgRef("lever", "blockedco"), http, QUERY)
    assert route.call_count == 1  # no retry, no evasion


@respx.mock
def test_bot_block_page_detected(http):
    respx.get("https://api.lever.co/v0/postings/interstitial").mock(
        return_value=Response(
            200,
            text="<html><title>Just a moment...</title>verify you are human</html>",
            headers={"content-type": "text/html"},
        )
    )
    with pytest.raises(SourceBlockedError):
        LeverSource().org_listings(OrgRef("lever", "interstitial"), http, QUERY)


def test_forbidden_sources_refuse():
    with pytest.raises(ForbiddenSourceError, match="(?i)paste"):
        LinkedInSource().search(QUERY, None, [])  # type: ignore[arg-type]
    with pytest.raises(ForbiddenSourceError):
        IndeedSource().search(QUERY, None, [])  # type: ignore[arg-type]


def test_jsonld_extraction():
    html = (FIXTURES / "jsonld_page.html").read_text()
    listings = extract_jobpostings_from_html(html, "https://wonka.example/careers")
    assert len(listings) == 1
    job = listings[0]
    assert job.title == "Confectionery Automation Engineer"
    assert job.company == "Wonka Industries"
    assert job.location == "Zurich, CH"
    assert job.salary_min == 110000 and job.salary_currency == "CHF" and job.salary_period == "year"
    assert job.education_level == "bachelor"
    assert job.posted_at is not None
    assert job.extra["direct_apply"] is True


def test_harvest_org_refs():
    urls = [
        "https://boards.greenhouse.io/acmecorp/jobs/4011001",
        "https://job-boards.greenhouse.io/other",
        "https://jobs.lever.co/globex/a1b2c3d4",
        "https://jobs.ashbyhq.com/initech/c3d4e5f6",
        "https://apply.workable.com/hooli/j/ABC123/",
        "https://jobs.smartrecruiters.com/PiedPiper/744000060001-frontend-engineer",
        "https://vandelay.recruitee.com/o/python-developer",
        "https://apply.workable.com/api/v1/whatever",  # must not harvest 'api'
        "https://example.com/not-an-ats",
    ]
    refs = harvest_org_refs(urls)
    pairs = {(r.ats, r.slug) for r in refs}
    assert ("greenhouse", "acmecorp") in pairs
    assert ("greenhouse", "other") in pairs
    assert ("lever", "globex") in pairs
    assert ("ashby", "initech") in pairs
    assert ("workable", "hooli") in pairs
    assert ("smartrecruiters", "piedpiper") in pairs
    assert ("recruitee", "vandelay") in pairs
    assert all(slug != "api" for _, slug in pairs)


def test_robots_disallow_respected(http):
    with respx.mock:
        respx.get("https://blocked.example/robots.txt").mock(
            return_value=Response(200, text="User-agent: *\nDisallow: /private/")
        )
        respx.get("https://blocked.example/private/page").mock(return_value=Response(200, text="hi"))
        respx.get("https://blocked.example/public").mock(return_value=Response(200, text="hi"))

        from app.sources.http import RobotsDisallowedError

        with pytest.raises(RobotsDisallowedError):
            http.get("https://blocked.example/private/page")
        assert http.get("https://blocked.example/public").status_code == 200


def test_per_host_pacing_enforced(engine):
    import time

    client = PoliteHttpClient()
    assert client.min_interval >= 1.0  # the hard floor survives configuration
    with respx.mock:
        respx.get("https://paced.example/a").mock(return_value=Response(200, text="a"))
        respx.get("https://paced.example/b").mock(return_value=Response(200, text="b"))
        start = time.monotonic()
        client.get("https://paced.example/a", respect_robots=False, use_cache=False)
        client.get("https://paced.example/b", respect_robots=False, use_cache=False)
        elapsed = time.monotonic() - start
    assert elapsed >= 1.0  # 1 req/s/host floor


@respx.mock
def test_response_cache_prevents_refetch(http):
    route = respx.get("https://cached.example/api").mock(
        return_value=Response(200, text='{"ok": true}')
    )
    http.get("https://cached.example/api", respect_robots=False)
    http.get("https://cached.example/api", respect_robots=False)
    assert route.call_count == 1
