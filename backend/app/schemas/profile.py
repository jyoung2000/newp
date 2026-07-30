from __future__ import annotations

import datetime as dt
from typing import Any, Literal

from pydantic import BaseModel, Field

EEO_CHOICES_NOTE = "Free-form because ATS option lists vary; 'decline' is the default."


class WorkExperienceIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    company: str = Field(min_length=1, max_length=200)
    location: str | None = None
    start_date: dt.date | None = None
    end_date: dt.date | None = None
    is_current: bool = False
    bullets: list[str] = Field(default_factory=list)
    # What employment-history sections ask for beyond a résumé's worth.
    manager_name: str | None = Field(default=None, max_length=200)
    manager_title: str | None = Field(default=None, max_length=200)
    manager_email: str | None = Field(default=None, max_length=320)
    manager_phone: str | None = Field(default=None, max_length=60)
    # None = not answered. Never defaulted — see models/profile.py.
    may_contact_employer: bool | None = None
    reason_for_leaving: str | None = Field(default=None, max_length=2000)
    summary: str | None = Field(default=None, max_length=5000)


class WorkExperienceOut(WorkExperienceIn):
    id: int
    order_index: int

    model_config = {"from_attributes": True}


class EducationIn(BaseModel):
    degree: str | None = None
    field_of_study: str | None = None
    school: str = Field(min_length=1, max_length=200)
    start_date: dt.date | None = None
    end_date: dt.date | None = None
    gpa: float | None = Field(default=None, ge=0, le=10)


class EducationOut(EducationIn):
    id: int
    order_index: int

    model_config = {"from_attributes": True}


class RecommendationIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    title: str | None = None
    relationship_to_user: str | None = None
    # Legacy single "email or phone" box; email/phone below supersede it.
    contact: str | None = None
    text: str | None = None
    file_id: int | None = None
    company: str | None = Field(default=None, max_length=200)
    email: str | None = Field(default=None, max_length=320)
    phone: str | None = Field(default=None, max_length=60)
    years_known: int | None = Field(default=None, ge=0, le=99)
    reference_type: Literal["professional", "personal"] | None = None
    may_contact: bool | None = None


class RecommendationOut(RecommendationIn):
    id: int

    model_config = {"from_attributes": True}


class LanguageItem(BaseModel):
    name: str
    proficiency: str | None = None  # e.g. native/fluent/professional/basic


class CertificationItem(BaseModel):
    name: str
    issuer: str | None = None
    year: int | None = None


class SkillYears(BaseModel):
    years: float = Field(ge=0, le=60)
    confirmed: bool = False


class ProfileUpdate(BaseModel):
    """Partial update; only provided fields change."""

    first_name: str | None = None
    last_name: str | None = None
    email: str | None = None
    phone: str | None = None
    address_line: str | None = None
    city: str | None = None
    state: str | None = None
    postal_code: str | None = None
    country: str | None = None
    linkedin_url: str | None = None
    portfolio_url: str | None = None
    github_url: str | None = None
    website_url: str | None = None
    pronouns: str | None = None

    authorized_countries: list[str] | None = None
    requires_sponsorship: bool | None = None
    work_model_preference: Literal["remote", "hybrid", "onsite", "any"] | None = None
    willing_to_relocate: bool | None = None
    salary_expectation_amount: int | None = Field(default=None, ge=0)
    salary_expectation_currency: str | None = None
    salary_expectation_period: Literal["year", "month", "hour"] | None = None
    current_compensation_amount: int | None = Field(default=None, ge=0)
    current_compensation_currency: str | None = None
    current_compensation_period: Literal["year", "month", "hour"] | None = None
    earliest_start_date: dt.date | None = None
    notice_period_days: int | None = Field(default=None, ge=0, le=365)
    total_years_experience: float | None = Field(default=None, ge=0, le=60)
    skills_years: dict[str, SkillYears] | None = None
    how_heard_default: str | None = None
    over_18: bool | None = None
    consent_background_check: bool | None = None
    consent_drug_screening: bool | None = None
    security_clearance: str | None = None
    languages: list[LanguageItem] | None = None
    shift_availability: list[str] | None = None
    licenses_certifications: list[CertificationItem] | None = None

    veteran_status: str | None = None
    disability_status: str | None = None
    gender: str | None = None
    race_ethnicity: str | None = None


class ProfileOut(BaseModel):
    id: int
    first_name: str | None
    last_name: str | None
    email: str | None
    phone: str | None
    address_line: str | None
    city: str | None
    state: str | None
    postal_code: str | None
    country: str | None
    linkedin_url: str | None
    portfolio_url: str | None
    github_url: str | None
    website_url: str | None
    pronouns: str | None
    authorized_countries: list[str]
    requires_sponsorship: bool | None
    work_model_preference: str | None
    willing_to_relocate: bool | None
    salary_expectation_amount: int | None
    salary_expectation_currency: str | None
    salary_expectation_period: str | None
    current_compensation_amount: int | None
    current_compensation_currency: str | None
    current_compensation_period: str | None
    earliest_start_date: dt.date | None
    notice_period_days: int | None
    total_years_experience: float | None
    skills_years: dict[str, Any]
    how_heard_default: str | None
    over_18: bool | None
    consent_background_check: bool | None
    consent_drug_screening: bool | None
    security_clearance: str | None
    languages: list[dict[str, Any]]
    shift_availability: list[str]
    licenses_certifications: list[dict[str, Any]]
    veteran_status: str
    disability_status: str
    gender: str
    race_ethnicity: str

    model_config = {"from_attributes": True}


class ProfileFull(BaseModel):
    profile: ProfileOut
    work_experiences: list[WorkExperienceOut]
    educations: list[EducationOut]
    recommendations: list[RecommendationOut]
    completeness: int  # 0–100
    completeness_missing: list[str]


class ReorderRequest(BaseModel):
    ids: list[int]
