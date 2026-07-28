"""schema.org/JobPosting JSON-LD extraction.

Employers deliberately publish this structured data on public careers pages
so it can be indexed. Fetches go through the polite client with robots.txt
respected — this is the one truly 'generic' fetch path in JobPilot.
"""
from __future__ import annotations

import json
from typing import Any

from bs4 import BeautifulSoup

from app.logging_conf import get_logger
from app.services.salary import ParsedSalary, parse_salary
from app.sources.base import RawListing
from app.sources.http import PoliteHttpClient
from app.sources.util import parse_iso, strip_html

log = get_logger(__name__)

EDUCATION_MAP = {
    "high school": "high_school",
    "associate": "associate",
    "bachelor": "bachelor",
    "master": "master",
    "postgraduate": "master",
    "doctor": "doctorate",
    "phd": "doctorate",
    "no requirements": "none",
}


def _iter_jobpostings(node: Any):
    if isinstance(node, list):
        for item in node:
            yield from _iter_jobpostings(item)
        return
    if not isinstance(node, dict):
        return
    node_type = node.get("@type")
    types = node_type if isinstance(node_type, list) else [node_type]
    if any(t == "JobPosting" for t in types if isinstance(t, str)):
        yield node
    for key in ("@graph", "mainEntity", "itemListElement"):
        if key in node:
            yield from _iter_jobpostings(node[key])
    if "item" in node:
        yield from _iter_jobpostings(node["item"])


def extract_jobpostings_from_html(html: str, page_url: str) -> list[RawListing]:
    soup = BeautifulSoup(html, "html.parser")
    listings: list[RawListing] = []
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = script.string or script.get_text()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            # Some sites embed multiple JSON objects or trailing commas;
            # skip rather than guess.
            continue
        for posting in _iter_jobpostings(data):
            listing = _to_listing(posting, page_url)
            if listing is not None:
                listings.append(listing)
    return listings


def _to_listing(posting: dict[str, Any], page_url: str) -> RawListing | None:
    title = posting.get("title")
    if not title:
        return None
    org = posting.get("hiringOrganization")
    if isinstance(org, dict):
        company = org.get("name") or "Unknown"
    elif isinstance(org, str):
        company = org
    else:
        company = "Unknown"

    location, remote = _location(posting)
    salary = _salary(posting)
    education = _education(posting)
    url = posting.get("url") or page_url
    direct_apply = posting.get("directApply")

    return RawListing(
        source="jsonld",
        external_id=str(posting.get("identifier", {}).get("value"))
        if isinstance(posting.get("identifier"), dict)
        else None,
        url=url,
        apply_url=url,
        title=str(title),
        company=str(company),
        location=location,
        remote=remote,
        posted_at=parse_iso(posting.get("datePosted")),
        description=strip_html(posting.get("description")),
        salary_raw=salary.raw,
        salary_min=salary.minimum,
        salary_max=salary.maximum,
        salary_currency=salary.currency,
        salary_period=salary.period,
        education_level=education,
        extra={
            "employment_type": posting.get("employmentType"),
            "direct_apply": direct_apply,
        },
    )


def _location(posting: dict[str, Any]) -> tuple[str | None, bool | None]:
    remote: bool | None = None
    location_type = posting.get("jobLocationType")
    if isinstance(location_type, str) and "telecommute" in location_type.lower():
        remote = True
    places = posting.get("jobLocation")
    if isinstance(places, dict):
        places = [places]
    parts: list[str] = []
    if isinstance(places, list):
        for place in places:
            if not isinstance(place, dict):
                continue
            address = place.get("address")
            if isinstance(address, dict):
                bits = [
                    address.get("addressLocality"),
                    address.get("addressRegion"),
                    address.get("addressCountry"),
                ]
                text = ", ".join(str(b) for b in bits if b)
                if text:
                    parts.append(text)
            elif isinstance(address, str):
                parts.append(address)
    return ("; ".join(dict.fromkeys(parts)) or None, remote)


def _salary(posting: dict[str, Any]) -> ParsedSalary:
    base = posting.get("baseSalary")
    if not isinstance(base, dict):
        return parse_salary(str(base) if base else None)
    currency = base.get("currency")
    value = base.get("value")
    if isinstance(value, dict):
        minimum = value.get("minValue") or value.get("value")
        maximum = value.get("maxValue") or value.get("value")
        unit = (value.get("unitText") or "").lower()
        period = {"hour": "hour", "day": "day", "week": "week", "month": "month", "year": "year"}.get(unit)
        try:
            return ParsedSalary(
                minimum=int(float(minimum)) if minimum is not None else None,
                maximum=int(float(maximum)) if maximum is not None else None,
                currency=str(currency) if currency else None,
                period=period,
                raw=None,
            )
        except (TypeError, ValueError):
            return ParsedSalary(currency=str(currency) if currency else None)
    return parse_salary(str(value) if value else None)


def _education(posting: dict[str, Any]) -> str | None:
    req = posting.get("educationRequirements")
    if isinstance(req, dict):
        req = req.get("credentialCategory") or req.get("name")
    if not req:
        return None
    lowered = str(req).lower()
    for needle, level in EDUCATION_MAP.items():
        if needle in lowered:
            return level
    return None


def fetch_jobpostings(url: str, http: PoliteHttpClient) -> list[RawListing]:
    """Fetch one page (robots-respecting) and extract its JobPosting data."""
    response = http.get(url, respect_robots=True)
    if response.status_code != 200:
        return []
    return extract_jobpostings_from_html(response.text, url)
