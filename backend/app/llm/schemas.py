"""Typed request/response schemas for every LLM task.

All model calls in JobPilot flow through these Pydantic models via
``client.messages.parse`` structured outputs, so responses are validated
against a strict JSON schema before any other code sees them.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

# --- Resume parsing ---------------------------------------------------------


class ParsedContact(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    email: str | None = None
    phone: str | None = None
    city: str | None = None
    state: str | None = None
    country: str | None = None
    linkedin_url: str | None = None
    github_url: str | None = None
    website_url: str | None = None


class ParsedExperience(BaseModel):
    title: str
    company: str
    location: str | None = None
    start_date: str | None = Field(default=None, description="ISO date or YYYY-MM")
    end_date: str | None = Field(default=None, description="ISO date, YYYY-MM, or null if current")
    is_current: bool = False
    bullets: list[str] = Field(default_factory=list)


class ParsedEducation(BaseModel):
    degree: str | None = None
    field_of_study: str | None = None
    school: str
    start_date: str | None = None
    end_date: str | None = None
    gpa: float | None = None


class ParsedSkill(BaseModel):
    name: str
    years: float | None = Field(
        default=None,
        description="Years of experience ONLY if directly evidenced by dated roles using the skill",
    )


class ParsedResume(BaseModel):
    """Structured resume parse. Presented to the user for review and
    confirmation before anything is used — never trusted silently."""

    contact: ParsedContact
    summary: str | None = None
    work_experiences: list[ParsedExperience] = Field(default_factory=list)
    educations: list[ParsedEducation] = Field(default_factory=list)
    skills: list[ParsedSkill] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    total_years_experience: float | None = None


# --- Listing enrichment -----------------------------------------------------


class ListingEnrichment(BaseModel):
    summary: str = Field(description="Three sentences, plain language")
    requirements: list[str] = Field(default_factory=list, description="Extracted requirements")
    education_level: str | None = Field(
        default=None,
        description="One of: none, high_school, associate, bachelor, master, doctorate, or null",
    )
    match_score: int = Field(ge=0, le=100)
    match_rationale: str = Field(description="One line grounded in the candidate's actual profile")


# --- Field mapping ----------------------------------------------------------


class FieldMapping(BaseModel):
    """Maps a detected form field to a value drawn from the user's data.

    The value must come from the provided profile/answers context. A field
    that cannot be answered from that context gets value=null — the model
    never invents an answer; unresolved fields become human interventions.
    """

    matched_key: str | None = Field(
        default=None, description="Canonical field key or saved-answer key this maps to, if any"
    )
    value: str | None = Field(
        default=None,
        description="The value to enter, drawn strictly from the provided context; null if absent",
    )
    option_match: str | None = Field(
        default=None, description="For select/radio: the exact option text to choose, else null"
    )
    confidence: float = Field(ge=0.0, le=1.0)
    is_knockout: bool = Field(
        description="True if this is an auto-reject filter (authorization, cert, clearance, years threshold, shift)"
    )
    is_eeo: bool = Field(description="True if this is an EEO/self-identification question")
    rationale: str = Field(description="One short sentence explaining the mapping")


class KnockoutClassification(BaseModel):
    is_knockout: bool
    category: str | None = Field(
        default=None,
        description="authorization/sponsorship/certification/license/clearance/years_threshold/shift/age/other",
    )
    rationale: str


# --- Free-text drafting -----------------------------------------------------


class DraftAnswer(BaseModel):
    """A drafted free-text answer. Drawn strictly from the user's own profile
    and resume; facts not present in the provided context must not appear."""

    text: str
    facts_used: list[str] = Field(
        default_factory=list, description="Which provided facts the draft relies on"
    )
