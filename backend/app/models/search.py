from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class SearchTarget(TimestampMixin, Base):
    __tablename__ = "search_targets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    title_terms: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    location: Mapped[str | None] = mapped_column(String(200))
    remote: Mapped[bool | None] = mapped_column(Boolean)
    salary_floor: Mapped[int | None] = mapped_column(Integer)
    education_level: Mapped[str | None] = mapped_column(String(60))
    posted_within_days: Mapped[int | None] = mapped_column(Integer)
    exclusions: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    sources: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)  # empty = all
    schedule_minutes: Mapped[int | None] = mapped_column(Integer)  # None = manual only
    notify_new: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_run_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


class JobListing(TimestampMixin, Base):
    __tablename__ = "job_listings"
    __table_args__ = (
        UniqueConstraint("user_id", "canonical_url", name="uq_job_listings_user_url"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source: Mapped[str] = mapped_column(String(40), nullable=False)
    external_id: Mapped[str | None] = mapped_column(String(200))
    canonical_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    apply_url: Mapped[str | None] = mapped_column(String(1000))
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    company: Mapped[str] = mapped_column(String(300), nullable=False)
    # Which of the user's saved roles this listing answered, when it arrived
    # through a role target. Stored rather than recomputed so the list can say
    # why a job is there even after the role is renamed or removed.
    matched_role: Mapped[str | None] = mapped_column(String(200))
    location: Mapped[str | None] = mapped_column(String(300))
    remote: Mapped[bool | None] = mapped_column(Boolean)
    salary_min: Mapped[int | None] = mapped_column(Integer)
    salary_max: Mapped[int | None] = mapped_column(Integer)
    salary_currency: Mapped[str | None] = mapped_column(String(8))
    salary_period: Mapped[str | None] = mapped_column(String(10))
    salary_raw: Mapped[str | None] = mapped_column(String(300))
    education_level: Mapped[str | None] = mapped_column(String(60))
    posted_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    description: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)
    requirements: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    match_score: Mapped[int | None] = mapped_column(Integer)  # 0–100
    match_rationale: Mapped[str | None] = mapped_column(Text)
    fetched_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    extra: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class DiscoveredOrg(TimestampMixin, Base):
    """Per-user growing table of ATS org slugs harvested from search-engine
    discovery and manual adds; feeds the board-API connectors."""

    __tablename__ = "discovered_orgs"
    __table_args__ = (UniqueConstraint("user_id", "ats", "slug", name="uq_discovered_orgs_slug"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ats: Mapped[str] = mapped_column(String(40), nullable=False)
    slug: Mapped[str] = mapped_column(String(200), nullable=False)
    company_name: Mapped[str | None] = mapped_column(String(300))
    last_seen_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class SourceState(TimestampMixin, Base):
    """Tracks per-source health (e.g. `blocked` after 401/403/429) so the UI
    can surface it and the fetcher backs off instead of retrying."""

    __tablename__ = "source_states"
    __table_args__ = (UniqueConstraint("user_id", "source", name="uq_source_states_user_source"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source: Mapped[str] = mapped_column(String(60), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="ok", nullable=False)  # ok/blocked/disabled
    detail: Mapped[str | None] = mapped_column(Text)
    blocked_until: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
