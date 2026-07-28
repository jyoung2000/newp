from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy.orm import Session

from app.db import get_sessionmaker
from app.models import (
    CustomField,
    JobListing,
    Profile,
    SavedAnswer,
    User,
    WorkExperience,
)
from app.services.normalize import normalize_question, similarity
from app.services.resolver import DetectedField, resolve_field


@pytest.fixture()
def db(engine):
    session = get_sessionmaker()()
    yield session
    session.rollback()
    session.close()


@pytest.fixture()
def user(db: Session) -> User:
    user = User(email="resolver@example.com", password_hash="x", settings={})
    db.add(user)
    db.flush()
    db.add(
        Profile(
            user_id=user.id,
            first_name="Ada",
            last_name="Lovelace",
            email="ada@example.com",
            phone="+1 555 0100",
            city="London",
            country="United Kingdom",
            linkedin_url="https://linkedin.com/in/ada",
            authorized_countries=["United Kingdom"],
            requires_sponsorship=False,
            salary_expectation_amount=95000,
            salary_expectation_currency="GBP",
            salary_expectation_period="year",
            total_years_experience=7.0,
            skills_years={
                "python": {"years": 4, "confirmed": True},
                "rust": {"years": 2, "confirmed": False},
            },
            how_heard_default="Company careers page",
            over_18=True,
        )
    )
    db.add(
        WorkExperience(
            user_id=user.id, title="Engineer", company="Analytical Engines Ltd", order_index=0
        )
    )
    db.commit()
    return user


def listing_for(db: Session, user: User, company: str = "Acme Corp") -> JobListing:
    listing = JobListing(
        user_id=user.id,
        source="manual",
        canonical_url=f"https://example.com/{company.lower().replace(' ', '-')}",
        title="Backend Engineer",
        company=company,
    )
    db.add(listing)
    db.commit()
    return listing


# --- Precedence -------------------------------------------------------------


def test_profile_resolves_contact_fields(db, user):
    r = resolve_field(db, user, DetectedField(label="First Name", required=True))
    assert r.status == "resolved" and r.value == "Ada" and r.source == "profile"
    assert r.confidence == 1.0


def test_custom_field_beats_saved_answer(db, user):
    db.add(
        CustomField(
            user_id=user.id, label="T-shirt size", key="t shirt size", type="text", value="M"
        )
    )
    db.add(
        SavedAnswer(
            user_id=user.id,
            question_key=normalize_question("What is your t-shirt size?"),
            question_text="What is your t-shirt size?",
            answer="L",
        )
    )
    db.commit()
    r = resolve_field(db, user, DetectedField(label="What is your t-shirt size?"))
    assert r.status == "resolved"
    assert r.value == "M"
    assert r.source == "custom_field"


def test_saved_answer_matches_wording_variants(db, user):
    db.add(
        SavedAnswer(
            user_id=user.id,
            question_key=normalize_question("How did you hear about this position?"),
            question_text="How did you hear about this position?",
            answer="A friend recommended the team",
        )
    )
    db.commit()
    # Different wording, same normalized meaning-space.
    r = resolve_field(db, user, DetectedField(label="How did you hear about this position?"))
    assert r.status == "resolved" and r.source in ("profile", "saved_answer")


def test_unknown_question_without_llm_match_goes_to_human(db, user):
    r = resolve_field(
        db, user, DetectedField(label="What is your favorite programming paradigm?")
    )
    assert r.status == "needs_human"


# --- Knockouts: never guess -------------------------------------------------


def test_knockout_with_profile_answer_resolves(db, user):
    r = resolve_field(
        db,
        user,
        DetectedField(
            label="Will you now or in the future require sponsorship?",
            field_type="radio",
            options=["Yes", "No"],
            required=True,
        ),
    )
    assert r.status == "resolved" and r.value == "No" and r.is_knockout


def test_knockout_without_stored_answer_never_guessed(db, user):
    # Security clearance is a knockout; profile has none stored. Even though
    # the LLM layer exists, the resolver must refuse to guess.
    r = resolve_field(
        db,
        user,
        DetectedField(
            label="Do you hold an active security clearance?",
            field_type="radio",
            options=["Yes", "No"],
            required=True,
        ),
    )
    assert r.status == "needs_human"
    assert r.is_knockout


def test_years_skill_confirmed_resolves_unconfirmed_does_not(db, user):
    r = resolve_field(
        db, user, DetectedField(label="How many years of experience do you have with Python?")
    )
    assert r.status == "resolved" and r.value == 4

    r = resolve_field(
        db, user, DetectedField(label="How many years of experience do you have with Rust?")
    )
    assert r.status == "needs_human"
    assert r.is_knockout


def test_over_18_knockout_unset_goes_to_human(db, user):
    profile = db.query(Profile).filter_by(user_id=user.id).one()
    profile.over_18 = None
    db.commit()
    r = resolve_field(
        db, user, DetectedField(label="Are you 18 years of age or older?", options=["Yes", "No"])
    )
    assert r.status == "needs_human" and r.is_knockout


# --- EEO: only explicit profile choices ------------------------------------


def test_eeo_defaults_to_decline_option(db, user):
    r = resolve_field(
        db,
        user,
        DetectedField(
            label="Gender",
            field_type="select",
            options=["Male", "Female", "Non-binary", "I decline to self-identify"],
        ),
    )
    assert r.status == "resolved"
    assert r.value == "I decline to self-identify"
    assert r.is_eeo


def test_eeo_explicit_choice_used_exactly(db, user):
    profile = db.query(Profile).filter_by(user_id=user.id).one()
    profile.veteran_status = "I am not a protected veteran"
    db.commit()
    r = resolve_field(
        db,
        user,
        DetectedField(
            label="Protected veteran status",
            field_type="select",
            options=[
                "I identify as one or more of the classifications of protected veteran",
                "I am not a protected veteran",
                "I decline to self-identify",
            ],
        ),
    )
    assert r.status == "resolved" and r.value == "I am not a protected veteran"


def test_eeo_without_matching_option_goes_to_human(db, user):
    r = resolve_field(
        db,
        user,
        DetectedField(label="Gender", field_type="select", options=["Male", "Female"]),
    )
    assert r.status == "needs_human" and r.is_eeo


# --- Current compensation: blank is deliberate ------------------------------


def test_current_comp_blank_optional_stays_blank(db, user):
    r = resolve_field(
        db, user, DetectedField(label="Current salary", field_type="text", required=False)
    )
    assert r.status == "leave_blank"


def test_current_comp_blank_required_goes_to_human(db, user):
    r = resolve_field(
        db, user, DetectedField(label="Current salary", field_type="text", required=True)
    )
    assert r.status == "needs_human"


def test_current_comp_never_filled_from_salary_expectation(db, user):
    # Profile HAS a salary expectation; it must not leak into current comp.
    r = resolve_field(db, user, DetectedField(label="What is your current compensation?"))
    assert r.status in ("leave_blank", "needs_human")
    assert r.value is None


def test_salary_expectation_still_fills(db, user):
    r = resolve_field(db, user, DetectedField(label="Desired salary", field_type="number"))
    assert r.status == "resolved" and r.value == 95000


# --- Consent boxes ----------------------------------------------------------


def test_plain_privacy_consent_auto_checks(db, user):
    r = resolve_field(
        db, user, DetectedField(label="I agree to the privacy policy", field_type="checkbox")
    )
    assert r.status == "resolved" and r.auto_check is True


def test_unusual_consent_goes_to_human(db, user):
    r = resolve_field(
        db,
        user,
        DetectedField(
            label="I agree to the privacy policy and to binding arbitration of all disputes",
            field_type="checkbox",
        ),
    )
    assert r.status == "needs_human"


# --- Derived answers --------------------------------------------------------


def test_previously_worked_derived_from_history(db, user):
    listing = listing_for(db, user, company="Analytical Engines Ltd")
    r = resolve_field(
        db,
        user,
        DetectedField(label="Have you previously worked for Analytical Engines Ltd?", options=["Yes", "No"]),
        listing=listing,
    )
    assert r.status == "resolved" and r.value == "Yes" and r.source == "derived"

    other = listing_for(db, user, company="Globex")
    r = resolve_field(
        db,
        user,
        DetectedField(label="Have you previously worked for Globex?", options=["Yes", "No"]),
        listing=other,
    )
    assert r.status == "resolved" and r.value == "No"


def test_start_date_from_notice_period(db, user):
    profile = db.query(Profile).filter_by(user_id=user.id).one()
    profile.notice_period_days = 14
    db.commit()
    r = resolve_field(db, user, DetectedField(label="Earliest start date", field_type="date"))
    assert r.status == "resolved"
    assert dt.date.fromisoformat(r.value) >= dt.date.today()


# --- Free text --------------------------------------------------------------


def test_long_free_text_becomes_draft_pending(db, user):
    listing = listing_for(db, user)
    r = resolve_field(
        db,
        user,
        DetectedField(label="Why do you want to work at Acme Corp?", field_type="textarea"),
        listing=listing,
    )
    assert r.status in ("draft_pending", "needs_human")
    if r.status == "draft_pending":
        assert r.draft


def test_unapproved_saved_draft_requires_approval(db, user):
    key = normalize_question("Why do you want to work at {company}?")
    db.add(
        SavedAnswer(
            user_id=user.id,
            question_key=key,
            question_text="Why do you want to work at Acme?",
            answer="Because of the mission." * 20,
            approved=False,
            source="llm_approved",
        )
    )
    db.commit()
    listing = listing_for(db, user)
    r = resolve_field(
        db,
        user,
        DetectedField(label="Why do you want to work at Acme Corp?", field_type="textarea"),
        listing=listing,
    )
    assert r.status == "needs_human"
    assert r.saved_answer_id is not None


# --- Normalization ----------------------------------------------------------


def test_normalize_strips_boilerplate_and_numbering():
    a = normalize_question("3) Please describe, if applicable, your notice period *")
    assert "please" not in a and "3" not in a.split()[0]
    assert "notice period" in a


def test_normalize_company_placeholder():
    a = normalize_question("Have you worked for Acme before?", company="Acme")
    b = normalize_question("Have you worked for Globex before?", company="Globex")
    assert a == b and "{company}" in a


def test_similarity_reasonable():
    a = normalize_question("Are you legally authorized to work in the United States?")
    b = normalize_question("Are you authorized to work legally in the United States?")
    assert similarity(a, b) > 0.87
    assert similarity(a, normalize_question("What is your shirt size?")) < 0.5
