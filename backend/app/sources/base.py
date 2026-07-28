"""Job source contract and registry."""
from __future__ import annotations

import datetime as dt
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from app.sources.http import PoliteHttpClient


@dataclass
class SearchQuery:
    terms: list[str]
    location: str | None = None
    remote: bool | None = None
    salary_floor: int | None = None
    education_level: str | None = None
    posted_within_days: int | None = None
    limit_per_source: int = 50


@dataclass
class RawListing:
    source: str
    url: str
    title: str
    company: str
    external_id: str | None = None
    apply_url: str | None = None
    location: str | None = None
    remote: bool | None = None
    salary_raw: str | None = None
    salary_min: int | None = None
    salary_max: int | None = None
    salary_currency: str | None = None
    salary_period: str | None = None
    education_level: str | None = None
    posted_at: dt.datetime | None = None
    description: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class OrgRef:
    """A per-user discovered ATS org slug (feeds the board connectors)."""

    ats: str
    slug: str
    company_name: str | None = None


class JobSource(ABC):
    """One place JobPilot may look for listings.

    `permission_basis` is a human-readable statement of why fetching from
    this source is permitted — it is surfaced in docs/SOURCES.md and the UI.
    """

    name: str = "base"
    label: str = "Base"
    permission_basis: str = ""
    requires_key: bool = False

    def is_configured(self) -> bool:
        return True

    @abstractmethod
    def search(
        self, query: SearchQuery, http: PoliteHttpClient, orgs: list[OrgRef]
    ) -> list[RawListing]:
        """Return raw listings. Raise SourceBlockedError to mark blocked."""


class ForbiddenSourceError(NotImplementedError):
    pass


class NotImplementedSource(JobSource):
    """A source JobPilot will not implement because the site's terms of
    service prohibit automated collection. This is a deliberate, permanent
    stub — do not add an implementation behind a flag. Users who want these
    boards should browse them normally and paste listings in manually
    (the `manual` source stores them happily)."""

    reason: str = ""

    def search(
        self, query: SearchQuery, http: PoliteHttpClient, orgs: list[OrgRef]
    ) -> list[RawListing]:
        raise ForbiddenSourceError(
            f"{self.label}: {self.reason} JobPilot does not scrape sites whose terms forbid it. "
            "Paste listings you find there via 'Add listing manually' instead."
        )


def matches_query(listing: RawListing, query: SearchQuery) -> bool:
    """Client-side filter for sources whose APIs can't filter server-side."""
    if query.terms:
        haystack = f"{listing.title} {listing.description or ''}".lower()
        if not any(term.lower() in haystack for term in query.terms):
            return False
    if query.remote is True and listing.remote is False:
        return False
    if query.location:
        loc = (listing.location or "").lower()
        wanted = query.location.lower()
        is_remote = listing.remote is True or "remote" in loc
        if wanted not in loc and not is_remote:
            return False
    if query.posted_within_days and listing.posted_at is not None:
        cutoff = dt.datetime.now(dt.UTC) - dt.timedelta(days=query.posted_within_days)
        posted = listing.posted_at
        if posted.tzinfo is None:
            posted = posted.replace(tzinfo=dt.UTC)
        if posted < cutoff:
            return False
    if query.salary_floor and listing.salary_max is not None:
        if listing.salary_max < query.salary_floor:
            return False
    return True
