"""Source registry. `get_sources()` returns every source JobPilot knows,
including the deliberately-forbidden stubs (so the UI can show why)."""
from __future__ import annotations

from app.sources.aggregators import (
    AdzunaSource,
    ArbeitnowSource,
    JoobleSource,
    RemotiveSource,
    TheMuseSource,
    USAJobsSource,
)
from app.sources.ats_boards import (
    AshbySource,
    GreenhouseSource,
    LeverSource,
    RecruiteeSource,
    SmartRecruitersSource,
    WorkableSource,
)
from app.sources.base import (
    ForbiddenSourceError,
    JobSource,
    NotImplementedSource,
    OrgRef,
    RawListing,
    SearchQuery,
)
from app.sources.forbidden import (
    GlassdoorSource,
    IndeedSource,
    LinkedInSource,
    MonsterSource,
    ZipRecruiterSource,
)
from app.sources.websearch import WebSearchDiscovery

ALL_SOURCES: list[JobSource] = [
    GreenhouseSource(),
    LeverSource(),
    AshbySource(),
    WorkableSource(),
    SmartRecruitersSource(),
    RecruiteeSource(),
    AdzunaSource(),
    JoobleSource(),
    USAJobsSource(),
    RemotiveSource(),
    ArbeitnowSource(),
    TheMuseSource(),
    WebSearchDiscovery(),
    LinkedInSource(),
    IndeedSource(),
    MonsterSource(),
    GlassdoorSource(),
    ZipRecruiterSource(),
]


def get_sources() -> list[JobSource]:
    return ALL_SOURCES


def get_source(name: str) -> JobSource | None:
    return next((s for s in ALL_SOURCES if s.name == name), None)


def searchable_sources() -> list[JobSource]:
    return [
        s
        for s in ALL_SOURCES
        if not isinstance(s, (NotImplementedSource, WebSearchDiscovery)) and s.is_configured()
    ]


__all__ = [
    "ALL_SOURCES",
    "ForbiddenSourceError",
    "JobSource",
    "NotImplementedSource",
    "OrgRef",
    "RawListing",
    "SearchQuery",
    "WebSearchDiscovery",
    "get_source",
    "get_sources",
    "searchable_sources",
]
