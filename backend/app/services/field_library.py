"""The canonical field library: the questions that dominate real ATS forms in
2026, pre-modeled so most applications resolve with zero interruptions.

Each entry knows how to recognize its question and how to answer it from the
user's structured profile. Entries never guess: a missing profile value means
the entry declines to answer and the resolver escalates (custom fields →
saved answers → LLM → human), with knockouts and EEO handled under stricter
rules in the resolver.
"""
from __future__ import annotations

import datetime as dt
import re
from collections.abc import Callable
from dataclasses import dataclass, field

from app.models import Profile, StoredFile, WorkExperience

# What kind of value an entry produces.
#   text/number/date -> typed into inputs
#   boolean          -> yes/no questions (mapped onto options by the executor)
#   file             -> upload fields (value is a file id)


@dataclass
class BuiltinAnswer:
    value: str | bool | int | float | None
    kind: str = "text"
    formatted: str | None = None  # display/typing form when it differs from value


@dataclass
class ResolveContext:
    profile: Profile
    work_experiences: list[WorkExperience]
    files: list[StoredFile]
    company: str | None = None
    location: str | None = None


@dataclass
class BuiltinField:
    key: str
    patterns: list[str]
    resolve: Callable[[ResolveContext], BuiltinAnswer | None]
    knockout: bool = False
    eeo: bool = False
    consent: bool = False
    kind: str = "text"
    _compiled: list[re.Pattern] = field(default_factory=list, repr=False)

    def matches(self, label: str) -> bool:
        if not self._compiled:
            self._compiled = [re.compile(p, re.IGNORECASE) for p in self.patterns]
        return any(p.search(label) for p in self._compiled)


def _text(value: str | None) -> BuiltinAnswer | None:
    return BuiltinAnswer(value=value) if value else None


def _bool(value: bool | None) -> BuiltinAnswer | None:
    if value is None:
        return None
    return BuiltinAnswer(value=value, kind="boolean", formatted="Yes" if value else "No")


def _full_name(ctx: ResolveContext) -> BuiltinAnswer | None:
    p = ctx.profile
    if p.first_name and p.last_name:
        return BuiltinAnswer(value=f"{p.first_name} {p.last_name}")
    return None


def _salary_expectation(ctx: ResolveContext) -> BuiltinAnswer | None:
    p = ctx.profile
    if p.salary_expectation_amount is None:
        return None
    cur = p.salary_expectation_currency or "USD"
    period = p.salary_expectation_period or "year"
    return BuiltinAnswer(
        value=p.salary_expectation_amount,
        kind="number",
        formatted=f"{p.salary_expectation_amount:,} {cur} per {period}",
    )


def _current_comp(ctx: ResolveContext) -> BuiltinAnswer | None:
    """Deliberately returns None when unset: a blank current-compensation
    field is a choice the user made. The resolver special-cases this key so
    it is never filled from any other source either."""
    p = ctx.profile
    if p.current_compensation_amount is None:
        return None
    cur = p.current_compensation_currency or "USD"
    period = p.current_compensation_period or "year"
    return BuiltinAnswer(
        value=p.current_compensation_amount,
        kind="number",
        formatted=f"{p.current_compensation_amount:,} {cur} per {period}",
    )


def _authorized(ctx: ResolveContext) -> BuiltinAnswer | None:
    countries = [c.strip().lower() for c in (ctx.profile.authorized_countries or [])]
    if not countries:
        return None
    # If the form names a country (via listing location/context), answer for
    # it; otherwise answer only when the user has any authorization on file
    # and the question is generic.
    target = (ctx.location or "").lower()
    if target:
        for c in countries:
            if c and (c in target or target in c):
                return _bool(True)
        # A stated location that is NOT in the list is a real "No" only if
        # the location is a country the user clearly lacks; too fuzzy —
        # decline and let a human answer.
        return None
    return _bool(True)


def _sponsorship(ctx: ResolveContext) -> BuiltinAnswer | None:
    return _bool(ctx.profile.requires_sponsorship)


def _previously_worked(ctx: ResolveContext) -> BuiltinAnswer | None:
    """Derived honestly from the user's own work history."""
    if not ctx.company:
        return None
    needle = ctx.company.strip().lower()
    if not needle:
        return None
    for exp in ctx.work_experiences:
        if needle in exp.company.lower() or exp.company.lower() in needle:
            return _bool(True)
    return _bool(False)


def _earliest_start(ctx: ResolveContext) -> BuiltinAnswer | None:
    d = ctx.profile.earliest_start_date
    if d is None and ctx.profile.notice_period_days is not None:
        d = dt.date.today() + dt.timedelta(days=ctx.profile.notice_period_days)
    if d is None:
        return None
    return BuiltinAnswer(value=d.isoformat(), kind="date", formatted=d.strftime("%m/%d/%Y"))


def _notice_period(ctx: ResolveContext) -> BuiltinAnswer | None:
    days = ctx.profile.notice_period_days
    if days is None:
        return None
    if days == 0:
        return BuiltinAnswer(value=0, kind="number", formatted="Immediately available")
    weeks = days // 7
    formatted = f"{weeks} week{'s' if weeks != 1 else ''}" if days % 7 == 0 and weeks else f"{days} days"
    return BuiltinAnswer(value=days, kind="number", formatted=formatted)


def _total_years(ctx: ResolveContext) -> BuiltinAnswer | None:
    years = ctx.profile.total_years_experience
    if years is None:
        return None
    display = int(years) if float(years).is_integer() else years
    return BuiltinAnswer(value=years, kind="number", formatted=str(display))


def _default_resume(ctx: ResolveContext) -> BuiltinAnswer | None:
    for f in ctx.files:
        if f.kind == "resume" and f.is_default_resume:
            return BuiltinAnswer(value=f.id, kind="file", formatted=f.filename)
    for f in ctx.files:
        if f.kind == "resume":
            return BuiltinAnswer(value=f.id, kind="file", formatted=f.filename)
    return None


def _cover_letter(ctx: ResolveContext) -> BuiltinAnswer | None:
    for f in ctx.files:
        if f.kind == "cover_letter":
            return BuiltinAnswer(value=f.id, kind="file", formatted=f.filename)
    return None


def _languages(ctx: ResolveContext) -> BuiltinAnswer | None:
    langs = ctx.profile.languages or []
    if not langs:
        return None
    parts = []
    for lang in langs:
        name = lang.get("name") if isinstance(lang, dict) else str(lang)
        prof = lang.get("proficiency") if isinstance(lang, dict) else None
        parts.append(f"{name} ({prof})" if prof else str(name))
    return BuiltinAnswer(value=", ".join(parts))


def _certifications(ctx: ResolveContext) -> BuiltinAnswer | None:
    certs = ctx.profile.licenses_certifications or []
    if not certs:
        return None
    names = [c.get("name", str(c)) if isinstance(c, dict) else str(c) for c in certs]
    return BuiltinAnswer(value=", ".join(names))


def _shift(ctx: ResolveContext) -> BuiltinAnswer | None:
    shifts = ctx.profile.shift_availability or []
    if not shifts:
        return None
    return BuiltinAnswer(value=", ".join(shifts))


def _work_model(ctx: ResolveContext) -> BuiltinAnswer | None:
    pref = ctx.profile.work_model_preference
    if not pref or pref == "any":
        return _text(pref and "Open to remote, hybrid, or onsite")
    return BuiltinAnswer(value=pref, formatted=pref.capitalize())


def _eeo(getter: Callable[[Profile], str]) -> Callable[[ResolveContext], BuiltinAnswer | None]:
    def resolve(ctx: ResolveContext) -> BuiltinAnswer | None:
        # Always answerable: defaults to "decline". Filled exactly and only
        # with what the user chose; never inferred from anything.
        return BuiltinAnswer(value=getter(ctx.profile), kind="eeo")

    return resolve


# Order matters: more specific patterns first (e.g. sponsorship before
# authorization, current compensation before salary expectation).
FIELD_LIBRARY: list[BuiltinField] = [
    # --- Contact block ------------------------------------------------------
    BuiltinField("first_name", [r"^first\s*name", r"given name"], lambda c: _text(c.profile.first_name)),
    BuiltinField("last_name", [r"^last\s*name", r"family name", r"surname"], lambda c: _text(c.profile.last_name)),
    BuiltinField("full_name", [r"^(?:full |your |legal )?name$", r"full name"], _full_name),
    BuiltinField("email", [r"e-?mail"], lambda c: _text(c.profile.email)),
    BuiltinField("phone", [r"phone", r"mobile number"], lambda c: _text(c.profile.phone)),
    BuiltinField("address", [r"street|address line|^address"], lambda c: _text(c.profile.address_line)),
    BuiltinField("city", [r"\bcity\b|\btown\b"], lambda c: _text(c.profile.city)),
    BuiltinField("state", [r"\bstate\b|province|region"], lambda c: _text(c.profile.state)),
    BuiltinField("postal_code", [r"zip|postal"], lambda c: _text(c.profile.postal_code)),
    BuiltinField("country", [r"\bcountry\b"], lambda c: _text(c.profile.country)),
    BuiltinField("pronouns", [r"pronoun"], lambda c: _text(c.profile.pronouns)),
    # --- Links --------------------------------------------------------------
    BuiltinField("linkedin", [r"linked\s*-?in"], lambda c: _text(c.profile.linkedin_url)),
    BuiltinField("github", [r"github"], lambda c: _text(c.profile.github_url)),
    BuiltinField("portfolio", [r"portfolio"], lambda c: _text(c.profile.portfolio_url)),
    BuiltinField("website", [r"website|personal site|url"], lambda c: _text(c.profile.website_url or c.profile.portfolio_url)),
    # --- Files --------------------------------------------------------------
    BuiltinField("resume_upload", [r"resume|\bcv\b|curriculum"], _default_resume, kind="file"),
    BuiltinField("cover_letter", [r"cover\s*letter"], _cover_letter, kind="file"),
    # --- Compensation (current comp BEFORE expectation; see resolver) -------
    BuiltinField(
        "current_compensation",
        [r"current (?:base )?(?:salary|compensation|pay|ctc)", r"present salary", r"salary history"],
        _current_comp,
        kind="number",
    ),
    BuiltinField(
        "salary_expectation",
        [r"(?:desired|expected|expectation).{0,20}(?:salary|compensation|pay)",
         r"salary (?:expectation|requirement|desired)", r"compensation expectation", r"pay expectation"],
        _salary_expectation,
        kind="number",
    ),
    # --- Authorization / sponsorship (knockouts) ----------------------------
    BuiltinField(
        "sponsorship",
        [r"sponsor", r"visa (?:sponsorship|support)"],
        _sponsorship,
        knockout=True, kind="boolean",
    ),
    BuiltinField(
        "work_authorization",
        [r"authoriz|legally (?:able|permitted|entitled) to work", r"right to work", r"work permit|eligible to work"],
        _authorized,
        knockout=True, kind="boolean",
    ),
    # --- Logistics ----------------------------------------------------------
    BuiltinField("work_model", [r"remote|hybrid|on-?site|work (?:model|arrangement|location preference)"], _work_model),
    BuiltinField("relocate", [r"reloc"], lambda c: _bool(c.profile.willing_to_relocate), kind="boolean"),
    BuiltinField("commute", [r"commut|able to (?:travel|come) to"], lambda c: None, kind="boolean"),
    BuiltinField("start_date", [r"start date|available to start|earliest.{0,15}start|availability date"], _earliest_start, kind="date"),
    BuiltinField("notice_period", [r"notice period"], _notice_period),
    # --- Experience ---------------------------------------------------------
    BuiltinField(
        "total_years_experience",
        [r"(?:total\s+)?years? of (?:professional |work |relevant )?experience(?!\s+(?:with|in|using))"],
        _total_years,
        kind="number",
    ),
    BuiltinField("previously_worked", [r"(?:previously|ever) (?:worked|been employed)", r"former (?:employee|team member)", r"worked (?:for|at|here).{0,20}before"], _previously_worked, kind="boolean"),
    BuiltinField("referral", [r"know anyone|referred by|referral|employee referral"], lambda c: None),
    BuiltinField("how_heard", [r"how did you (?:hear|find|learn)", r"source of (?:application|referral)"], lambda c: _text(c.profile.how_heard_default)),
    # --- Compliance (knockout-graded) ---------------------------------------
    BuiltinField("over_18", [r"18 (?:years|or older)|at least 18|minimum age|legal age"], lambda c: _bool(c.profile.over_18), knockout=True, kind="boolean"),
    BuiltinField("background_check", [r"background (?:check|screening|investigation)"], lambda c: _bool(c.profile.consent_background_check), consent=True, kind="boolean"),
    BuiltinField("drug_screening", [r"drug (?:test|screen)"], lambda c: _bool(c.profile.consent_drug_screening), consent=True, kind="boolean"),
    BuiltinField("security_clearance", [r"clearance"], lambda c: _text(c.profile.security_clearance), knockout=True),
    # --- EEO self-identification -------------------------------------------
    BuiltinField("eeo_gender", [r"\bgender\b|\bsex\b"], _eeo(lambda p: p.gender), eeo=True),
    BuiltinField("eeo_race", [r"race|ethnicit|hispanic or latino"], _eeo(lambda p: p.race_ethnicity), eeo=True),
    BuiltinField("eeo_veteran", [r"veteran|vevraa|protected veteran"], _eeo(lambda p: p.veteran_status), eeo=True),
    BuiltinField("eeo_disability", [r"disabilit|section 503"], _eeo(lambda p: p.disability_status), eeo=True),
    # --- Misc ---------------------------------------------------------------
    BuiltinField("languages", [r"language"], _languages),
    BuiltinField("certifications", [r"certification|licen[cs]es?\b"], _certifications),
    BuiltinField("shift_availability", [r"shift|weekend|night|schedule availability"], _shift),
    # --- Consents (auto-check ONLY the plain standard ones; see resolver) ---
    BuiltinField(
        "privacy_consent",
        [r"privacy (?:policy|notice)", r"terms of (?:application|service|use)", r"consent to (?:the )?processing"],
        lambda c: BuiltinAnswer(value=True, kind="consent"),
        consent=True,
    ),
    BuiltinField(
        "ai_screening_consent",
        [r"ai|automated (?:screening|processing|decision)"],
        lambda c: BuiltinAnswer(value=True, kind="consent"),
        consent=True,
    ),
]

# Patterns for "years of experience with <skill>" questions.
YEARS_SKILL = re.compile(
    r"(?:how many\s+)?years?(?: of)?(?: professional| work| hands.on| relevant)? experience"
    r"(?:\s+do you have)?\s+(?:with|in|using)\s+(?P<skill>[A-Za-z0-9+#./ -]{2,40})",
    re.IGNORECASE,
)


def match_builtin(label: str) -> BuiltinField | None:
    for entry in FIELD_LIBRARY:
        if entry.matches(label):
            return entry
    return None


def match_years_skill(label: str, profile: Profile) -> BuiltinAnswer | None:
    """'Years of experience with X' — answered only from the user-confirmed
    skills_years map; anything else is a human question."""
    m = YEARS_SKILL.search(label)
    if not m:
        return None
    skill = m.group("skill").strip().rstrip("?").strip().lower()
    for name, meta in (profile.skills_years or {}).items():
        if not isinstance(meta, dict) or not meta.get("confirmed"):
            continue
        if name.lower() == skill or name.lower() in skill or skill in name.lower():
            years = meta.get("years")
            if years is None:
                return None
            display = int(years) if float(years).is_integer() else years
            return BuiltinAnswer(value=years, kind="number", formatted=str(display))
    # Recognized the shape but have no confirmed answer -> decline (the
    # resolver treats years-threshold questions as knockout-adjacent).
    return BuiltinAnswer(value=None, kind="number")
