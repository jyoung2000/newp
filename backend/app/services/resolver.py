"""The resolver: one implementation shared by both executors.

For each detected form field it resolves, in order:
    structured profile (field library) → custom fields → saved answers →
    LLM mapping → human intervention.

Hard rules enforced here, regardless of mode or confidence:
  * Knockout questions are answered only from explicit stored data. No LLM
    guess is ever accepted for them — a missing answer becomes an
    intervention.
  * EEO questions are filled exactly and only from the user's profile
    choices (defaulting to decline-to-self-identify); never inferred.
  * A blank current-compensation profile field is a deliberate choice: it is
    never auto-filled. Optional fields stay blank; required ones go to the
    human.
  * Only plain, standard privacy/terms checkboxes are auto-checked; unusual
    consent language goes to the human.
  * Generated free-text answers above the trivial length require one-time
    user approval per job family before auto-mode reuse.
"""
from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field as dc_field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.llm import tasks as llm_tasks
from app.llm.config import LLMConfig, config_for_user
from app.llm.fakes import classify_knockout_heuristic
from app.logging_conf import get_logger
from app.models import (
    CustomField,
    JobListing,
    Profile,
    SavedAnswer,
    StoredFile,
    User,
    WorkExperience,
    utcnow,
)
from app.services import field_library as lib
from app.services.normalize import (
    FUZZY_MATCH_THRESHOLD,
    label_similarity,
    normalize_question,
    similarity,
)

log = get_logger(__name__)

# Consent checkboxes containing any of these are never auto-checked.
UNUSUAL_CONSENT_MARKERS = (
    "arbitration", "waive", "waiver", "release", "non-compete", "noncompete",
    "credit check", "marketing", "newsletter", "promotional", "sell my",
    "biometric", "geolocation", "third part", "sms", "text message",
)

FREE_TEXT_TYPES = ("textarea",)


@dataclass
class DetectedField:
    """What an executor reports about one form field."""

    label: str
    field_type: str = "text"  # text/textarea/select/radio/checkbox/file/number/date/email/tel
    options: list[str] = dc_field(default_factory=list)
    required: bool = False
    name: str | None = None  # HTML name/id attribute
    surrounding_text: str = ""


@dataclass
class Resolution:
    status: str  # resolved / leave_blank / needs_human / draft_pending
    value: Any = None
    formatted: str | None = None
    kind: str = "text"
    source: str = "none"  # profile/derived/custom_field/saved_answer/llm/none
    confidence: float = 0.0
    field_key: str | None = None
    is_knockout: bool = False
    is_eeo: bool = False
    auto_check: bool = False
    reason: str = ""
    draft: str | None = None
    saved_answer_id: int | None = None


@dataclass
class UserData:
    profile: Profile
    work_experiences: list[WorkExperience]
    files: list[StoredFile]
    custom_fields: list[CustomField]
    saved_answers: list[SavedAnswer]
    # The requesting user's own AI credentials/model (Settings → AI),
    # falling back to the environment configuration.
    llm_config: LLMConfig | None = None


def load_user_data(db: Session, user: User) -> UserData:
    profile = db.scalar(select(Profile).where(Profile.user_id == user.id))
    assert profile is not None, "every user has a profile row"
    return UserData(
        llm_config=config_for_user(user),
        profile=profile,
        work_experiences=list(
            db.scalars(
                select(WorkExperience)
                .where(WorkExperience.user_id == user.id)
                .order_by(WorkExperience.order_index)
            )
        ),
        files=list(db.scalars(select(StoredFile).where(StoredFile.user_id == user.id))),
        custom_fields=list(
            db.scalars(select(CustomField).where(CustomField.user_id == user.id))
        ),
        saved_answers=list(
            db.scalars(select(SavedAnswer).where(SavedAnswer.user_id == user.id))
        ),
    )


def build_llm_context(data: UserData) -> str:
    """'key: value' lines of everything the user has stored — the ONLY facts
    the LLM may draw from."""
    p = data.profile
    lines: list[str] = []

    def add(key: str, value: Any) -> None:
        if value is None or value == "" or value == []:
            return
        lines.append(f"{key}: {value}")

    add("first_name", p.first_name)
    add("last_name", p.last_name)
    add("email", p.email)
    add("phone", p.phone)
    add("address", p.address_line)
    add("city", p.city)
    add("state", p.state)
    add("postal_code", p.postal_code)
    add("country", p.country)
    add("linkedin_url", p.linkedin_url)
    add("github_url", p.github_url)
    add("portfolio_url", p.portfolio_url)
    add("website_url", p.website_url)
    add("work_model_preference", p.work_model_preference)
    add("willing_to_relocate", p.willing_to_relocate)
    add("total_years_experience", p.total_years_experience)
    add("how_heard_default", p.how_heard_default)
    add("languages", p.languages)
    add("shift_availability", p.shift_availability)
    add("licenses_certifications", p.licenses_certifications)
    if p.salary_expectation_amount is not None:
        add(
            "salary_expectation",
            f"{p.salary_expectation_amount} {p.salary_expectation_currency or 'USD'}"
            f" per {p.salary_expectation_period or 'year'}",
        )
    for exp in data.work_experiences:
        add(
            f"work_experience ({exp.title})",
            f"{exp.title} at {exp.company}" + (", current" if exp.is_current else ""),
        )
    for skill, meta in (p.skills_years or {}).items():
        if isinstance(meta, dict) and meta.get("confirmed"):
            add(f"skill_years ({skill})", meta.get("years"))
    for cf in data.custom_fields:
        if cf.value is not None:
            add(f"custom ({cf.label})", cf.value)
    for sa in data.saved_answers:
        if sa.approved:
            add(f"saved_answer ({sa.question_key[:80]})", sa.answer)
    # NOTE deliberately absent: EEO fields, current compensation. The LLM
    # never sees them, so it can never leak them into an answer.
    return "\n".join(lines)


def _is_unusual_consent(label: str, surrounding: str) -> bool:
    text = f"{label} {surrounding}".lower()
    return any(marker in text for marker in UNUSUAL_CONSENT_MARKERS)


def _eeo_resolution(entry: lib.BuiltinField, answer: lib.BuiltinAnswer, field_: DetectedField) -> Resolution:
    """EEO: the stored choice ('decline' by default) mapped onto the form's
    own options. No option match -> human."""
    choice = str(answer.value)
    option = _match_eeo_option(choice, field_.options)
    if field_.options and option is None:
        return Resolution(
            status="needs_human",
            field_key=entry.key,
            is_eeo=True,
            reason=f"No form option matches the stored choice {choice!r}",
        )
    return Resolution(
        status="resolved",
        value=option or choice,
        formatted=option or choice,
        kind="select" if field_.options else "text",
        source="profile",
        confidence=1.0,
        field_key=entry.key,
        is_eeo=True,
        reason="EEO self-identification from explicit profile choice",
    )


_DECLINE_SYNONYMS = (
    "decline", "do not wish", "don't wish", "prefer not", "not to answer",
    "not to disclose", "not to self-identify", "no answer", "i don't wish",
)


def _match_eeo_option(choice: str, options: list[str]) -> str | None:
    if not options:
        return None
    lowered = choice.lower()
    if lowered == "decline":
        for opt in options:
            if any(s in opt.lower() for s in _DECLINE_SYNONYMS):
                return opt
        return None
    for opt in options:
        if lowered == opt.lower() or lowered in opt.lower():
            return opt
    return None


def _match_option(value: Any, formatted: str | None, options: list[str]) -> str | None:
    """Map a stored value onto one of the form's options, conservatively."""
    if not options:
        return None
    candidates = [str(value), formatted or ""]
    if isinstance(value, bool):
        candidates = ["yes" if value else "no", formatted or ""]
    for cand in candidates:
        if not cand:
            continue
        for opt in options:
            if opt.strip().lower() == cand.strip().lower():
                return opt
    for cand in candidates:
        if not cand:
            continue
        for opt in options:
            ol = opt.strip().lower()
            cl = cand.strip().lower()
            if (cl and cl in ol) or (ol and ol in cl):
                return opt
    return None


def resolve_field(
    db: Session,
    user: User,
    field_: DetectedField,
    listing: JobListing | None = None,
    data: UserData | None = None,
) -> Resolution:
    data = data or load_user_data(db, user)
    settings = get_settings()
    company = listing.company if listing else None
    location = listing.location if listing else None
    ctx = lib.ResolveContext(
        profile=data.profile,
        work_experiences=data.work_experiences,
        files=data.files,
        company=company,
        location=location,
    )
    label = field_.label.strip() or (field_.name or "")
    normalized = normalize_question(label, company=company, location=location)

    # Knockout classification up front (heuristic; LLM refines later). EEO is
    # detected by the library entries and the LLM mapping downstream.
    knockout = classify_knockout_heuristic(label).is_knockout

    # --- 1a. Years-per-skill (more specific than any library entry) --------
    years = lib.match_years_skill(label, data.profile)
    if years is not None:
        if years.value is not None:
            return Resolution(
                status="resolved", value=years.value, formatted=years.formatted,
                kind="number", source="profile", confidence=1.0,
                field_key="years_skill", is_knockout=knockout,
                reason="Confirmed per-skill years from profile",
            )
        # Recognized but unanswered: knockout-adjacent. Stored answers may
        # still cover it; the LLM may not.
        stored = _from_custom_or_saved(normalized, label, field_, data, db, knockout=True)
        if stored is not None:
            return stored
        return Resolution(
            status="needs_human", field_key="years_skill", is_knockout=True,
            reason="Years-of-experience question without a confirmed stored answer",
        )

    # --- 1b. Field library (structured profile) -----------------------------
    entry = lib.match_builtin(label) or (lib.match_builtin(field_.name) if field_.name else None)
    if entry is not None:
        knockout = knockout or entry.knockout
        answer = entry.resolve(ctx)

        if entry.eeo:
            assert answer is not None  # EEO entries always produce the stored choice
            return _eeo_resolution(entry, answer, field_)

        if entry.key in ("privacy_consent", "ai_screening_consent"):
            if _is_unusual_consent(label, field_.surrounding_text):
                return Resolution(
                    status="needs_human", field_key=entry.key,
                    reason="Non-standard consent language — a human must read it",
                )
            return Resolution(
                status="resolved", value=True, kind="consent", source="profile",
                confidence=1.0, field_key=entry.key, auto_check=True,
                reason="Standard privacy/terms consent",
            )

        if entry.key == "current_compensation" and answer is None:
            # Blank on purpose. Never derived, never guessed. Explicit custom
            # fields / saved answers (below) are the only other lawful source.
            resolution = _from_custom_or_saved(normalized, label, field_, data, db, knockout=True)
            if resolution is not None:
                return resolution
            if field_.required:
                return Resolution(
                    status="needs_human", field_key=entry.key, is_knockout=True,
                    reason="Current compensation is blank in the profile by choice; the form requires it",
                )
            return Resolution(
                status="leave_blank", field_key=entry.key,
                reason="Current compensation left blank by user choice",
            )

        if answer is not None and answer.value is not None:
            option = _match_option(answer.value, answer.formatted, field_.options)
            if field_.options and option is None:
                return Resolution(
                    status="needs_human", field_key=entry.key, is_knockout=knockout,
                    reason=f"Stored value {answer.formatted or answer.value!r} matches no form option",
                )
            return Resolution(
                status="resolved",
                value=option if option is not None else answer.value,
                formatted=option or answer.formatted or str(answer.value),
                kind="select" if option is not None else (answer.kind if answer.kind != "eeo" else "text"),
                source="derived" if entry.key == "previously_worked" else "profile",
                confidence=1.0,
                field_key=entry.key,
                is_knockout=knockout,
                reason=f"Field library: {entry.key}",
            )
        # Library recognized the field but the profile lacks the value —
        # fall through to custom fields / saved answers.

    # --- 2 & 3. Custom fields, then saved answers ---------------------------
    resolution = _from_custom_or_saved(normalized, label, field_, data, db, knockout=knockout)
    if resolution is not None:
        return resolution

    # Knockouts stop here: no stored answer means a human answers. Never an
    # LLM guess, in either mode, at any confidence.
    if knockout:
        return Resolution(
            status="needs_human",
            field_key=entry.key if entry else None,
            is_knockout=True,
            reason="Knockout question with no stored answer — refusing to guess",
        )

    # --- 4. Free-text drafting ---------------------------------------------
    if field_.field_type in FREE_TEXT_TYPES:
        return _draft_resolution(field_, normalized, data, listing, settings.freetext_trivial_length)

    # --- 5. LLM mapping -----------------------------------------------------
    context = build_llm_context(data)
    try:
        mapping = llm_tasks.map_field(
            label,
            field_.field_type,
            field_.options,
            field_.surrounding_text,
            context,
            config=data.llm_config,
        )
    except Exception as exc:  # LLM unavailable -> human, never a guess
        log.warning("resolver.llm_failed", error=str(exc))
        return Resolution(status="needs_human", reason=f"LLM mapping unavailable: {exc}")

    if mapping.is_eeo:
        return Resolution(
            status="needs_human", is_eeo=True,
            reason="EEO-classified question outside the library — human decides",
        )
    if mapping.is_knockout:
        # LLM says knockout and nothing stored answered it above.
        return Resolution(
            status="needs_human", is_knockout=True,
            reason="LLM classified this as a knockout question — refusing to guess",
        )
    threshold = float(
        (user.settings or {}).get("resolver_confidence_threshold")
        or settings.resolver_confidence_threshold
    )
    if mapping.value is None or mapping.confidence < threshold:
        return Resolution(
            status="needs_human",
            reason=mapping.rationale or "No confident mapping from stored data",
            confidence=mapping.confidence,
        )
    value = mapping.option_match if field_.options else mapping.value
    if field_.options and mapping.option_match is None:
        return Resolution(
            status="needs_human", confidence=mapping.confidence,
            reason="LLM found data but no exact option correspondence",
        )
    return Resolution(
        status="resolved", value=value, formatted=str(value),
        kind="select" if field_.options else "text",
        source="llm", confidence=mapping.confidence,
        field_key=mapping.matched_key, reason=mapping.rationale,
    )


def _from_custom_or_saved(
    normalized: str,
    label: str,
    field_: DetectedField,
    data: UserData,
    db: Session,
    knockout: bool,
) -> Resolution | None:
    # Custom fields: match against normalized key or label. Same priority as
    # built-ins per spec — they are checked immediately after.
    best_cf, best_cf_score = None, 0.0
    for cf in data.custom_fields:
        if cf.value is None:
            continue
        score = max(
            label_similarity(normalized, normalize_question(cf.label)),
            label_similarity(normalized, cf.key.replace("_", " ")),
        )
        if score > best_cf_score:
            best_cf, best_cf_score = cf, score
    if best_cf is not None and best_cf_score >= FUZZY_MATCH_THRESHOLD:
        value = best_cf.value
        option = _match_option(value, None, field_.options)
        if field_.options and option is None:
            return Resolution(
                status="needs_human", field_key=best_cf.key, is_knockout=knockout,
                reason=f"Custom field '{best_cf.label}' matches no form option",
            )
        return Resolution(
            status="resolved", value=option if option is not None else value,
            formatted=option or str(value),
            kind="select" if option is not None else best_cf.type,
            source="custom_field", confidence=1.0, field_key=best_cf.key,
            is_knockout=knockout, reason=f"Custom field '{best_cf.label}'",
        )

    best_sa, best_sa_score = None, 0.0
    for sa in data.saved_answers:
        score = similarity(normalized, sa.question_key)
        if score > best_sa_score:
            best_sa, best_sa_score = sa, score
    if best_sa is not None and best_sa_score >= FUZZY_MATCH_THRESHOLD:
        if not best_sa.approved:
            return Resolution(
                status="needs_human", field_key=best_sa.question_key,
                is_knockout=knockout, saved_answer_id=best_sa.id,
                draft=str(best_sa.answer),
                reason="Saved draft answer awaiting user approval",
            )
        value = best_sa.answer
        option = _match_option(value, None, field_.options)
        if field_.options and option is None:
            return Resolution(
                status="needs_human", field_key=best_sa.question_key, is_knockout=knockout,
                reason="Saved answer matches no form option",
            )
        return Resolution(
            status="resolved", value=option if option is not None else value,
            formatted=option or str(value), kind="select" if option is not None else best_sa.answer_type,
            source="saved_answer", confidence=1.0 if best_sa_score >= 0.99 else 0.97,
            field_key=best_sa.question_key, is_knockout=knockout,
            saved_answer_id=best_sa.id,
            reason=f"Saved answer (match {best_sa_score:.2f})",
        )
    return None


def _draft_resolution(
    field_: DetectedField,
    normalized: str,
    data: UserData,
    listing: JobListing | None,
    trivial_length: int,
) -> Resolution:
    listing_context = ""
    if listing is not None:
        listing_context = f"{listing.title} at {listing.company}\n{listing.summary or (listing.description or '')[:2000]}"
    context = build_llm_context(data)
    resume_text = next(
        (f.extracted_text for f in data.files if f.kind == "resume" and f.is_default_resume and f.extracted_text),
        "",
    )
    if resume_text:
        context += f"\n\nresume_text: {resume_text[:8000]}"
    try:
        draft = llm_tasks.draft_answer(
            field_.label, context, listing_context, config=data.llm_config
        )
    except Exception as exc:
        return Resolution(status="needs_human", reason=f"Draft generation unavailable: {exc}")
    if len(draft.text) <= trivial_length:
        return Resolution(
            status="resolved", value=draft.text, formatted=draft.text, kind="text",
            source="llm", confidence=0.8, field_key=normalized,
            reason="Trivial-length generated answer",
        )
    return Resolution(
        status="draft_pending", draft=draft.text, kind="text", source="llm",
        confidence=0.0, field_key=normalized,
        reason="Generated free-text answer requires one-time approval",
    )


def mark_answer_used(db: Session, saved_answer_id: int, listing: JobListing | None) -> None:
    sa = db.get(SavedAnswer, saved_answer_id)
    if sa is None:
        return
    sa.times_used += 1
    sa.last_used_at = utcnow()
    history = list(sa.asked_history or [])
    history.append(
        {
            "url": listing.canonical_url if listing else None,
            "company": listing.company if listing else None,
            "at": utcnow().isoformat(),
        }
    )
    sa.asked_history = history[-50:]
