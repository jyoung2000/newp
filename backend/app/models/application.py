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
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

# Application status values. Transition rules live in app/executor/states.py.
APP_STATUSES = (
    "draft",
    "queued",
    "filling",
    "needs_human",
    "submitting",
    "submitted",
    "submitted_unconfirmed",
    "drafted",  # draft-only mode terminal: filled + screenshotted, never submitted
    "failed",
    "skipped",
    "stopped",
)
APP_MODES = ("auto", "review", "draft")
EXECUTORS = ("extension", "playwright")
NEEDS_HUMAN_REASONS = ("challenge", "unknown_field", "review", "login", "error", "draft_approval")
OUTCOMES = ("none", "no_response", "rejected", "recruiter_reply", "interview", "offer")


class RunBatch(TimestampMixin, Base):
    __tablename__ = "run_batches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    mode: Mapped[str] = mapped_column(String(10), nullable=False)
    executor: Mapped[str | None] = mapped_column(String(20))  # None = auto-pick
    humanize: Mapped[bool | None] = mapped_column(Boolean)  # None = user default
    status: Mapped[str] = mapped_column(String(20), default="running", nullable=False)
    # running / paused / stopped / completed
    settings_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    started_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))

    applications = relationship("Application", back_populates="run_batch")


class Application(TimestampMixin, Base):
    __tablename__ = "applications"
    # One application per user per posting, ever.
    __table_args__ = (UniqueConstraint("user_id", "listing_id", name="uq_applications_user_listing"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    listing_id: Mapped[int] = mapped_column(
        ForeignKey("job_listings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    run_batch_id: Mapped[int | None] = mapped_column(
        ForeignKey("run_batches.id", ondelete="SET NULL"), index=True
    )
    status: Mapped[str] = mapped_column(String(30), default="draft", nullable=False, index=True)
    mode: Mapped[str] = mapped_column(String(10), default="review", nullable=False)
    executor: Mapped[str | None] = mapped_column(String(20))
    humanize: Mapped[bool | None] = mapped_column(Boolean)
    resume_file_id: Mapped[int | None] = mapped_column(ForeignKey("files.id", ondelete="SET NULL"))
    needs_human_reason: Mapped[str | None] = mapped_column(String(30))
    # Set when the intervention window lapsed and the runner moved on.
    parked_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    submitted_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    field_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    confirmation_screenshot_path: Mapped[str | None] = mapped_column(String(500))
    error: Mapped[str | None] = mapped_column(Text)
    outcome: Mapped[str] = mapped_column(String(20), default="none", nullable=False)
    outcome_updated_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))

    run_batch = relationship("RunBatch", back_populates="applications")
    listing = relationship("JobListing")
    events = relationship(
        "ApplicationEvent", back_populates="application", cascade="all, delete-orphan"
    )
    interventions = relationship(
        "Intervention", back_populates="application", cascade="all, delete-orphan"
    )


class ApplicationEvent(Base):
    """Append-only audit trail for every application."""

    __tablename__ = "application_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    application_id: Mapped[int] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), nullable=False, index=True
    )
    type: Mapped[str] = mapped_column(String(60), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    application = relationship("Application", back_populates="events")


class Intervention(TimestampMixin, Base):
    __tablename__ = "interventions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    application_id: Mapped[int] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    # unknown_field / challenge / review / draft_approval / error
    question: Mapped[str | None] = mapped_column(Text)
    field_meta: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    screenshot_path: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(20), default="open", nullable=False, index=True)
    # open / answered / resolved / expired / cancelled
    answer: Mapped[Any | None] = mapped_column(JSON)
    resolved_by: Mapped[str | None] = mapped_column(String(20))  # user / timeout
    resolved_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    saved_to_kb: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    application = relationship("Application", back_populates="interventions")
