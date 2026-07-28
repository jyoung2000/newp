from __future__ import annotations

from typing import Any

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin

FILE_KINDS = ("resume", "cover_letter", "certification", "portfolio", "screenshot")


class StoredFile(TimestampMixin, Base):
    __tablename__ = "files"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    filename: Mapped[str] = mapped_column(String(400), nullable=False)
    content_type: Mapped[str] = mapped_column(String(120), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    # Path relative to UPLOAD_DIR, always beginning with the owner's user id —
    # the storage service enforces the scoping (services/storage.py).
    path: Mapped[str] = mapped_column(String(500), nullable=False)
    is_default_resume: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # LLM parse of a resume; used only after the user confirms it.
    parsed_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    parse_confirmed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    extracted_text: Mapped[str | None] = mapped_column(String)  # plain text for LLM context
