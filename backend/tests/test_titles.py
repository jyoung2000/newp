"""Job-title variation matching.

The failure modes are asymmetric. Missing a variation costs the user a job they
never saw. Matching too loosely fills their list with jobs they don't want,
which is the failure that makes the whole feature useless — so the
should-not-match cases below matter at least as much as the should-match ones.
"""
from __future__ import annotations

import pytest

from app.services import titles


@pytest.mark.parametrize(
    "raw,level,head,modifiers",
    [
        ("Software Engineer", None, "engineer", {"software"}),
        ("Sr. Software Engineer II", "senior", "engineer", {"software"}),
        ("SWE", None, "engineer", {"software"}),
        ("Senior Backend Developer (Remote)", "senior", "engineer", {"software"}),
        ("Engineering Manager", None, "manager", {"software"}),
        ("Manager of Engineering", None, "manager", {"software"}),
        ("Registered Nurse", None, "nurse", {"healthcare"}),
        ("Data Analyst", None, "analyst", {"data"}),
        # A director is a job, not a seniority prefix on another one.
        ("Engineering Director", None, "director", {"software"}),
        ("VP of Engineering", None, "executive", {"software"}),
        ("Full-Time Junior QA Tester", "junior", "engineer", {"quality"}),
    ],
)
def test_shape_reduces_a_title_to_level_head_and_modifiers(raw, level, head, modifiers):
    s = titles.shape(raw)
    assert s.level == level
    assert s.head == head
    assert set(s.modifiers) == modifiers


@pytest.mark.parametrize(
    "wanted,candidate",
    [
        # The same job said differently.
        ("Software Engineer", "Software Developer"),
        ("Software Engineer", "Software Programmer"),
        ("Software Engineer", "SWE"),
        ("Software Engineer", "Sr. Software Engineer"),
        ("Software Engineer", "Software Engineer II"),
        ("Software Engineer", "Senior Software Developer (Remote)"),
        ("Software Engineer", "Backend Engineer"),
        ("Software Engineer", "Full Stack Developer"),
        ("Software Developer", "Software Engineer"),
        # Level noise in either direction.
        ("Senior Data Analyst", "Data Analyst"),
        ("Data Analyst", "Junior Data Analyst"),
        # Abbreviations.
        ("Site Reliability Engineer", "SRE"),
        ("Registered Nurse", "RN"),
        ("Customer Service Representative", "CSR"),
        # Vaguer or more specific versions of the same role.
        ("Engineer", "Mechanical Engineer"),
        ("Software Engineer", "Engineer"),
        # A domain this module has never heard of still works by word overlap.
        ("Sommelier", "Head Sommelier"),
    ],
)
def test_variations_match(wanted, candidate):
    value = titles.score(wanted, candidate)
    assert value >= titles.TITLE_MATCH_THRESHOLD, f"{candidate!r} should match {wanted!r} (got {value})"


@pytest.mark.parametrize(
    "wanted,candidate",
    [
        # Same word, different job. This is the pairing that makes or breaks
        # the feature: "engineer" appears in both.
        ("Software Engineer", "Engineering Manager"),
        ("Software Engineer", "Sales Engineer"),
        ("Software Engineer", "Engineering Director"),
        ("Software Developer", "Business Development Manager"),
        # Adjacent but genuinely different roles.
        ("Data Analyst", "Data Scientist"),
        ("Data Analyst", "Data Engineer"),
        ("Product Manager", "Project Manager"),
        ("Registered Nurse", "Nurse Practitioner Manager"),
        # Unrelated.
        ("Software Engineer", "Truck Driver"),
        ("Software Engineer", "Marketing Coordinator"),
        ("Accountant", "Account Executive"),
    ],
)
def test_different_jobs_do_not_match(wanted, candidate):
    value = titles.score(wanted, candidate)
    assert value < titles.TITLE_MATCH_THRESHOLD, f"{candidate!r} must NOT match {wanted!r} (got {value})"


def test_identical_titles_score_one():
    assert titles.score("Software Engineer", "software engineer") == 1.0
    assert titles.score("Sr. Software Engineer", "Senior Software Engineer") == 1.0


def test_empty_input_never_matches():
    assert titles.score("", "Software Engineer") == 0.0
    assert titles.score("Software Engineer", "") == 0.0
    assert titles.best_match([], "Software Engineer") == (None, 0.0)
    assert titles.best_match(["  "], "Software Engineer") == (None, 0.0)


def test_best_match_reports_which_role_a_listing_answers():
    wanted = ["Software Engineer", "Data Analyst", "Product Manager"]
    role, value = titles.best_match(wanted, "Senior Backend Developer")
    assert role == "Software Engineer"
    assert value >= titles.TITLE_MATCH_THRESHOLD

    role, value = titles.best_match(wanted, "Junior Data Analyst (Hybrid)")
    assert role == "Data Analyst"

    role, value = titles.best_match(wanted, "Head Chef")
    assert role is None or value < titles.TITLE_MATCH_THRESHOLD


def test_the_closest_role_wins_when_several_could_match():
    wanted = ["Engineer", "Software Engineer"]
    role, value = titles.best_match(wanted, "Software Engineer")
    assert role == "Software Engineer" and value == 1.0


def test_expand_offers_readable_variations_starting_with_what_was_typed():
    out = titles.expand("Software Engineer")
    assert out[0] == "Software Engineer"
    lowered = [v.lower() for v in out]
    assert "software developer" in lowered
    assert "software programmer" in lowered
    # Readable phrases, not internal family names.
    assert all("machinelearning" not in v for v in lowered)
    assert len(out) <= 6


def test_expand_keeps_the_users_own_wording():
    out = titles.expand("Sr. Backend Engineer")
    assert out[0] == "Sr. Backend Engineer"
    # Variations reuse the words the user wrote, not canonical families.
    assert any(v.lower() == "backend developer" for v in out)


def test_expand_handles_a_title_with_no_known_head_noun():
    out = titles.expand("Sommelier")
    assert out == ["Sommelier"]


def test_expanded_variations_all_match_the_original_role():
    """Whatever expand() offers the user must actually pass the gate — the two
    halves of this module have to agree, or the UI promises matches the search
    then rejects."""
    for role in [
        "Software Engineer",
        "Data Analyst",
        "Registered Nurse",
        "Marketing Coordinator",
        "Mechanical Engineer",
        "Customer Service Representative",
    ]:
        for variation in titles.expand(role):
            assert titles.matches([role], variation), f"{variation!r} from expand({role!r})"


def test_matches_respects_a_custom_threshold():
    # Same head, unrelated domains scores 0.4 — excluded by default, reachable
    # if a caller deliberately widens the net.
    assert not titles.matches(["Software Engineer"], "Sales Engineer")
    assert titles.matches(["Software Engineer"], "Sales Engineer", threshold=0.3)
