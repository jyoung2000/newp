from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import JSON, Boolean, Date, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

# EEO self-identification values. "decline" is the default everywhere and the
# resolver only ever fills what the user explicitly chose — never inferred.
EEO_DECLINE = "decline"


class Profile(TimestampMixin, Base):
    __tablename__ = "profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )

    # --- Personal block -------------------------------------------------
    first_name: Mapped[str | None] = mapped_column(String(120))
    last_name: Mapped[str | None] = mapped_column(String(120))
    email: Mapped[str | None] = mapped_column(String(320))
    phone: Mapped[str | None] = mapped_column(String(50))
    address_line: Mapped[str | None] = mapped_column(String(255))
    city: Mapped[str | None] = mapped_column(String(120))
    state: Mapped[str | None] = mapped_column(String(120))
    postal_code: Mapped[str | None] = mapped_column(String(20))
    country: Mapped[str | None] = mapped_column(String(120))
    linkedin_url: Mapped[str | None] = mapped_column(String(400))
    portfolio_url: Mapped[str | None] = mapped_column(String(400))
    github_url: Mapped[str | None] = mapped_column(String(400))
    website_url: Mapped[str | None] = mapped_column(String(400))
    pronouns: Mapped[str | None] = mapped_column(String(60))  # user-supplied only

    # --- Application defaults (the 2026 field library) -------------------
    # Countries where the user is legally authorized to work.
    authorized_countries: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    requires_sponsorship: Mapped[bool | None] = mapped_column(Boolean)
    work_model_preference: Mapped[str | None] = mapped_column(String(20))  # remote/hybrid/onsite/any
    willing_to_relocate: Mapped[bool | None] = mapped_column(Boolean)
    salary_expectation_amount: Mapped[int | None] = mapped_column(Integer)
    salary_expectation_currency: Mapped[str | None] = mapped_column(String(8))
    salary_expectation_period: Mapped[str | None] = mapped_column(String(10))  # year/month/hour
    # Deliberately separate from expectation. Blank means "the user chose not
    # to disclose" and the resolver never fills it (see services/resolver.py).
    current_compensation_amount: Mapped[int | None] = mapped_column(Integer)
    current_compensation_currency: Mapped[str | None] = mapped_column(String(8))
    current_compensation_period: Mapped[str | None] = mapped_column(String(10))
    earliest_start_date: Mapped[dt.date | None] = mapped_column(Date)
    notice_period_days: Mapped[int | None] = mapped_column(Integer)
    total_years_experience: Mapped[float | None] = mapped_column(Float)
    # {"python": {"years": 4, "confirmed": true}, ...} — mapped from the
    # resume, then confirmed by the user before use.
    skills_years: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    how_heard_default: Mapped[str | None] = mapped_column(String(200))
    over_18: Mapped[bool | None] = mapped_column(Boolean)
    consent_background_check: Mapped[bool | None] = mapped_column(Boolean)
    consent_drug_screening: Mapped[bool | None] = mapped_column(Boolean)
    security_clearance: Mapped[str | None] = mapped_column(String(120))
    languages: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    shift_availability: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    licenses_certifications: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, default=list, nullable=False
    )

    # --- EEO self-identification (US VEVRAA / Section 503 forms) ---------
    # All default to decline-to-self-identify; filled only as the user chose.
    veteran_status: Mapped[str] = mapped_column(String(60), default=EEO_DECLINE, nullable=False)
    disability_status: Mapped[str] = mapped_column(String(60), default=EEO_DECLINE, nullable=False)
    gender: Mapped[str] = mapped_column(String(60), default=EEO_DECLINE, nullable=False)
    race_ethnicity: Mapped[str] = mapped_column(String(120), default=EEO_DECLINE, nullable=False)

    user = relationship("User", back_populates="profile")


class WorkExperience(TimestampMixin, Base):
    __tablename__ = "work_experiences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    company: Mapped[str] = mapped_column(String(200), nullable=False)
    location: Mapped[str | None] = mapped_column(String(200))
    start_date: Mapped[dt.date | None] = mapped_column(Date)
    end_date: Mapped[dt.date | None] = mapped_column(Date)
    is_current: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    bullets: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class Education(TimestampMixin, Base):
    __tablename__ = "educations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    degree: Mapped[str | None] = mapped_column(String(200))
    field_of_study: Mapped[str | None] = mapped_column(String(200))
    school: Mapped[str] = mapped_column(String(200), nullable=False)
    start_date: Mapped[dt.date | None] = mapped_column(Date)
    end_date: Mapped[dt.date | None] = mapped_column(Date)
    gpa: Mapped[float | None] = mapped_column(Float)
    order_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class Recommendation(TimestampMixin, Base):
    __tablename__ = "recommendations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    title: Mapped[str | None] = mapped_column(String(200))
    relationship_to_user: Mapped[str | None] = mapped_column(String(200))
    contact: Mapped[str | None] = mapped_column(String(320))
    text: Mapped[str | None] = mapped_column(Text)
    file_id: Mapped[int | None] = mapped_column(ForeignKey("files.id", ondelete="SET NULL"))
