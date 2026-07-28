from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin

CUSTOM_FIELD_TYPES = ("text", "number", "date", "boolean", "select", "file")
SAVED_ANSWER_SOURCES = ("user", "imported", "intervention", "llm_approved")


class CustomField(TimestampMixin, Base):
    """User-defined fields. First-class citizens in the resolver with the
    same priority as built-in profile fields."""

    __tablename__ = "custom_fields"
    __table_args__ = (UniqueConstraint("user_id", "key", name="uq_custom_fields_user_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    label: Mapped[str] = mapped_column(String(300), nullable=False)
    key: Mapped[str] = mapped_column(String(300), nullable=False)  # normalized from label
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    options: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    value: Mapped[Any | None] = mapped_column(JSON)
    file_id: Mapped[int | None] = mapped_column(ForeignKey("files.id", ondelete="SET NULL"))


class SavedAnswer(TimestampMixin, Base):
    """The knowledge base: every answered question, reusable forever."""

    __tablename__ = "saved_answers"
    __table_args__ = (
        UniqueConstraint("user_id", "question_key", name="uq_saved_answers_user_question"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    question_key: Mapped[str] = mapped_column(String(500), nullable=False)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[Any] = mapped_column(JSON, nullable=False)
    answer_type: Mapped[str] = mapped_column(String(20), default="text", nullable=False)
    times_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_used_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    source: Mapped[str] = mapped_column(String(20), default="user", nullable=False)
    # Free-text LLM drafts require explicit approval before auto-mode reuse.
    approved: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # e.g. "why_company" — groups draft approvals per job family.
    job_family: Mapped[str | None] = mapped_column(String(120))
    # [{"url": ..., "company": ..., "at": iso8601}, ...]
    asked_history: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
