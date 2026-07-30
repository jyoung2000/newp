from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, false
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    totp_secret: Mapped[str | None] = mapped_column(String(64))
    totp_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # The head admin. Granted to the first account registered on an install
    # (see api/auth.register) and thereafter only by an existing admin. Admins
    # manage accounts; they get no access to another user's job data, which
    # stays isolated by user_id at the query layer.
    # false() renders per dialect (`false` on Postgres, `0` on SQLite).
    is_admin: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, server_default=false()
    )

    # --- AI provider settings (Settings → AI) ---------------------------
    # The API key is stored encrypted (services/crypto.py) and is never
    # returned to a client in plaintext — only a masked hint. When unset,
    # JobPilot falls back to the ANTHROPIC_API_KEY environment variable.
    llm_api_key_enc: Mapped[str | None] = mapped_column(String(500))
    llm_model: Mapped[str | None] = mapped_column(String(80))
    # True = deterministic offline heuristics; nothing is sent to the LLM.
    llm_offline: Mapped[bool | None] = mapped_column(Boolean)
    # User-scoped settings: notification channels, humanize default,
    # resolver confidence threshold, run-mode default, timezone, etc.
    settings: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    profile = relationship(
        "Profile", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    sessions = relationship("UserSession", back_populates="user", cascade="all, delete-orphan")


class UserSession(Base):
    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    csrf_token: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(400))
    revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Set when a password is verified but TOTP is still pending.
    totp_pending: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    user = relationship("User", back_populates="sessions")
