"""Employment-history and reference groups: detection, indexing, resolution.

The detection layer is the risky part of this feature, in both directions. A
miss means the user is asked for something they already entered. A false
positive is worse: it types one person's details into another person's box.
Both directions are asserted here.
"""
from __future__ import annotations

import datetime as dt

import pytest

from app.models import Recommendation, WorkExperience
from app.services import groups
from tests.conftest import register_and_login


def _job(**kw) -> WorkExperience:
    defaults = dict(
        user_id=1,
        title="Staff Engineer",
        company="Analytical Engines Ltd",
        location="London",
        start_date=dt.date(2019, 3, 1),
        end_date=dt.date(2023, 6, 30),
        is_current=False,
        bullets=["Wrote the first program"],
        order_index=0,
        manager_name="Charles Babbage",
        manager_title="Director of Engines",
        manager_email="charles@engines.example",
        manager_phone="+44 20 7000 0001",
        may_contact_employer=True,
        reason_for_leaving="Took a role with more scope",
        summary="Built and maintained the analytical engine's program tables.",
    )
    defaults.update(kw)
    return WorkExperience(**defaults)


def _ref(**kw) -> Recommendation:
    defaults = dict(
        user_id=1,
        name="Mary Somerville",
        title="Professor",
        relationship_to_user="Former manager",
        company="Royal Society",
        email="mary@rs.example",
        phone="+44 20 7000 0002",
        years_known=7,
        reference_type="professional",
        may_contact=True,
    )
    defaults.update(kw)
    return Recommendation(**defaults)


# --- Detection --------------------------------------------------------------


@pytest.mark.parametrize(
    "label,name,surrounding,kind,attribute,index",
    [
        # Indexed name attributes, the way ATS forms post arrays. Brackets are
        # 0-based; a number a human typed is 1-based.
        ("Company", "work_history[0][company]", "", groups.EMPLOYER, "company", 0),
        ("Company", "work_history[1][company]", "", groups.EMPLOYER, "company", 1),
        ("Supervisor", "employer_2_supervisor", "", groups.EMPLOYER, "manager_name", 1),
        ("Name", "references[0][name]", "", groups.REFERENCE, "name", 0),
        ("Phone", "reference_3_phone", "", groups.REFERENCE, "phone", 2),
        # Numbered labels.
        ("Employer 2 — Reason for leaving", None, "", groups.EMPLOYER, "reason_for_leaving", 1),
        ("Reference #3 Email", None, "", groups.REFERENCE, "email", 2),
        ("Second employer: job title", None, "", groups.EMPLOYER, "title", 1),
        ("Most recent employer", None, "", groups.EMPLOYER, "company", 0),
        # The block says which group; the field says which attribute. This is
        # the common real-world shape — the legend is in the surrounding text
        # and the input has its own plain label.
        ("Email", "ref_email", "References — Reference 1", groups.REFERENCE, "email", 0),
        ("Relationship", None, "Professional references", groups.REFERENCE, "relationship_to_user", None),
        ("Reason for leaving", None, "Employment history", groups.EMPLOYER, "reason_for_leaving", None),
        ("Supervisor name", None, "Previous employer", groups.EMPLOYER, "manager_name", None),
        # Attributes that only exist inside a group.
        ("May we contact this employer?", None, "", groups.EMPLOYER, "may_contact_employer", None),
        ("How long have you known them?", None, "Reference 2", groups.REFERENCE, "years_known", 1),
        ("Job duties", None, "Work history", groups.EMPLOYER, "summary", None),
        ("Dates employed from", None, "Employment history", groups.EMPLOYER, "start_date", None),
        ("Employed to", None, "Employment history", groups.EMPLOYER, "end_date", None),
    ],
)
def test_detects_group_fields(label, name, surrounding, kind, attribute, index):
    found = groups.detect(label, name, surrounding)
    assert found is not None, f"{label!r} / {name!r} should be a {kind} field"
    assert found.kind == kind
    assert found.attribute == attribute
    assert found.index == index


@pytest.mark.parametrize(
    "label,name,surrounding",
    [
        # The applicant's own details. None of these may be captured by a group.
        ("Email", "email", ""),
        ("First name", "first_name", ""),
        ("Phone", "phone", ""),
        ("City", "city", ""),
        ("Your email address", "applicant_email", "Employment history"),
        ("Applicant phone", None, "References"),
        # "Referred by" / "referral" is how-did-you-hear, not a reference.
        ("Were you referred by an employee?", "referral", ""),
        ("Referral source", None, ""),
        # A reference number is an identifier, not a person.
        ("Reference number", "ref_no", ""),
        # In a group, but nothing identifiable to fill — better asked than
        # guessed from a neighbouring field.
        ("Salary at leaving", None, "Employment history"),
    ],
)
def test_does_not_claim_fields_that_are_not_group_fields(label, name, surrounding):
    assert groups.detect(label, name, surrounding) is None


# --- Indexing across a whole form -------------------------------------------


def test_unnumbered_repeats_are_numbered_by_order():
    """Three identical reference blocks, no numbers anywhere. Their order in
    the form is the only thing that tells them apart."""
    fields = [("Name", "References"), ("Email", "References")] * 3
    detected = [groups.detect(label, None, surrounding) for label, surrounding in fields]
    groups.assign_indices(detected)
    assert [d.index for d in detected] == [0, 0, 1, 1, 2, 2]


def test_explicit_indices_are_not_overwritten_and_later_blanks_follow_them():
    detected = [
        groups.detect("Reference 1 name", None, ""),
        groups.detect("Reference 2 name", None, ""),
        groups.detect("Name", None, "References"),  # third block, unnumbered
    ]
    groups.assign_indices(detected)
    assert [d.index for d in detected] == [0, 1, 2]


def test_non_group_fields_are_left_alone_by_indexing():
    detected = [groups.detect("Email", "email", ""), groups.detect("Name", None, "References")]
    groups.assign_indices(detected)
    assert detected[0] is None
    assert detected[1].index == 0


# --- Resolution -------------------------------------------------------------


def test_resolves_every_employer_attribute():
    jobs = [_job()]
    def answer(label, surrounding=""):
        g = groups.detect(label, None, surrounding)
        assert g is not None, label
        a = groups.resolve(g, jobs, [])
        return a.value if a else None

    assert answer("Employer 1 company") == "Analytical Engines Ltd"
    assert answer("Employer 1 job title") == "Staff Engineer"
    assert answer("Supervisor name", "Employment history") == "Charles Babbage"
    assert answer("Supervisor title", "Employment history") == "Director of Engines"
    assert answer("Supervisor email", "Employment history") == "charles@engines.example"
    assert answer("Supervisor phone", "Employment history") == "+44 20 7000 0001"
    assert answer("May we contact this employer?") is True
    assert answer("Reason for leaving", "Employment history") == "Took a role with more scope"
    assert answer("Job duties", "Employment history").startswith("Built and maintained")
    assert answer("Start date", "Employment history") == "2019-03-01"
    assert answer("End date", "Employment history") == "2023-06-30"


def test_resolves_every_reference_attribute():
    refs = [_ref()]
    def answer(label, surrounding="References"):
        g = groups.detect(label, None, surrounding)
        assert g is not None, label
        a = groups.resolve(g, [], refs)
        return a.value if a else None

    assert answer("Name") == "Mary Somerville"
    assert answer("Title") == "Professor"
    assert answer("Company") == "Royal Society"
    assert answer("Relationship") == "Former manager"
    assert answer("Email") == "mary@rs.example"
    assert answer("Phone") == "+44 20 7000 0002"
    assert answer("How long have you known them?") == 7
    assert answer("May we contact them?") is True


def test_the_second_employer_answers_from_the_second_entry():
    jobs = [_job(company="First Co"), _job(company="Second Co", manager_name="Second Boss")]
    g = groups.detect("Employer 2 company", None, "")
    assert groups.resolve(g, jobs, []).value == "Second Co"
    g = groups.detect("Employer 2 supervisor", None, "")
    assert groups.resolve(g, jobs, []).value == "Second Boss"


def test_a_current_job_reports_present_rather_than_a_blank_end_date():
    jobs = [_job(is_current=True, end_date=None)]
    g = groups.detect("End date", None, "Employment history")
    assert groups.resolve(g, jobs, []).value == "Present"


def test_missing_entries_and_blank_fields_return_nothing():
    """Nothing to say is the correct answer when the entry doesn't exist or the
    user left that part empty — the field then goes to the human."""
    jobs = [_job(manager_name=None, reason_for_leaving=None)]
    assert groups.resolve(groups.detect("Employer 3 company", None, ""), jobs, []) is None
    assert groups.resolve(groups.detect("Supervisor", None, "Employment history"), jobs, []) is None
    assert (
        groups.resolve(groups.detect("Reason for leaving", None, "Work history"), jobs, []) is None
    )
    assert groups.resolve(groups.detect("Name", None, "References"), jobs, []) is None


def test_unanswered_may_contact_is_not_defaulted():
    """A tri-state that must stay tri-state: not answered is not 'no', and
    certainly not 'yes'."""
    jobs = [_job(may_contact_employer=None)]
    assert groups.resolve(groups.detect("May we contact this employer?", None, ""), jobs, []) is None
    refs = [_ref(may_contact=None)]
    g = groups.detect("May we contact them?", None, "References")
    assert groups.resolve(g, [], refs) is None


def test_a_summary_falls_back_to_bullets_rather_than_leaving_it_blank():
    jobs = [_job(summary=None, bullets=["Led a team of five", "Shipped the engine"])]
    g = groups.detect("Describe your duties", None, "Employment history")
    assert groups.resolve(g, jobs, []).value == "Led a team of five. Shipped the engine."


def test_legacy_combined_contact_still_answers_email_and_phone():
    """References entered before email/phone were separate fields kept one
    combined 'contact' value. It should still answer both kinds of box."""
    g_email = groups.detect("Email", None, "References")
    g_phone = groups.detect("Phone", None, "References")
    with_email = [_ref(email=None, phone=None, contact="old@example.com")]
    assert groups.resolve(g_email, [], with_email).value == "old@example.com"
    assert groups.resolve(g_phone, [], with_email) is None
    with_phone = [_ref(email=None, phone=None, contact="555-0100")]
    assert groups.resolve(g_phone, [], with_phone).value == "555-0100"
    assert groups.resolve(g_email, [], with_phone) is None


# --- Through the real resolver ----------------------------------------------


def test_reference_email_does_not_get_the_applicants_own_address(client, engine):
    """The bug this layer exists to prevent: the flat field library's e-mail
    pattern matches 'Reference 1 email', so without group detection running
    first the applicant's own address is typed into their reference's box."""
    from sqlalchemy.orm import Session

    from app.models import Profile, User
    from app.services.resolver import DetectedField, resolve_field

    register_and_login(client, "applicant@example.com")
    with Session(engine) as db:
        user = db.scalars(__import__("sqlalchemy").select(User)).first()
        profile = db.scalar(
            __import__("sqlalchemy").select(Profile).where(Profile.user_id == user.id)
        )
        profile.email = "applicant@example.com"
        db.add(_ref(user_id=user.id))
        db.commit()

        own = resolve_field(db, user, DetectedField(label="Email", name="email"))
        assert own.value == "applicant@example.com"

        theirs = resolve_field(
            db,
            user,
            DetectedField(label="Reference 1 email", name="references[0][email]"),
        )
        assert theirs.value == "mary@rs.example"
        assert theirs.field_key == "reference.email"


def test_an_empty_group_field_asks_the_user_and_says_which_entry(client, engine):
    from sqlalchemy import select
    from sqlalchemy.orm import Session

    from app.models import User
    from app.services.resolver import DetectedField, resolve_field

    register_and_login(client, "empty@example.com")
    with Session(engine) as db:
        user = db.scalars(select(User)).first()
        db.add(_job(user_id=user.id, manager_name=None))
        db.commit()
        got = resolve_field(
            db,
            user,
            DetectedField(label="Supervisor name", surrounding_text="Employment history"),
        )
        assert got.status == "needs_human"
        assert "employer 1" in got.reason.lower()
        assert "Profile → Work" in got.reason
