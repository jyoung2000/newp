from __future__ import annotations

import datetime as dt

import pytest

from app.db import get_sessionmaker
from app.executor.captcha import check_html, is_login_url
from app.executor.states import (
    TERMINAL,
    InvalidTransitionError,
    transition,
)
from app.models import Application, JobListing, Profile, User, utcnow


@pytest.fixture()
def db(engine):
    session = get_sessionmaker()()
    yield session
    session.rollback()
    session.close()


@pytest.fixture()
def app_row(db):
    user = User(email="exec@example.com", password_hash="x", settings={})
    db.add(user)
    db.flush()
    db.add(Profile(user_id=user.id))
    listing = JobListing(
        user_id=user.id, source="manual", canonical_url="https://x/1", title="T", company="C"
    )
    db.add(listing)
    db.flush()
    app = Application(
        user_id=user.id, listing_id=listing.id, status="draft", mode="auto"
    )
    db.add(app)
    db.flush()
    return db, user, app


# --- State machine ----------------------------------------------------------


def test_happy_path_transitions(app_row):
    db, user, app = app_row
    transition(db, app, "queued")
    transition(db, app, "filling")
    transition(db, app, "submitting")
    transition(db, app, "submitted")
    assert app.status == "submitted"
    assert app.submitted_at is not None
    types = [e.type for e in app.events]
    assert "status.queued" in types and "status.submitted" in types


def test_illegal_transition_rejected(app_row):
    db, user, app = app_row
    with pytest.raises(InvalidTransitionError):
        transition(db, app, "submitted")  # draft -> submitted not allowed


def test_terminal_states_are_dead_ends(app_row):
    db, user, app = app_row
    transition(db, app, "queued")
    transition(db, app, "filling")
    transition(db, app, "submitting")
    transition(db, app, "submitted")
    for target in ("queued", "submitting", "submitted", "filling"):
        with pytest.raises(InvalidTransitionError):
            transition(db, app, target)
    assert "submitted" in TERMINAL


def test_needs_human_roundtrip_clears_reason(app_row):
    db, user, app = app_row
    transition(db, app, "queued")
    transition(db, app, "filling")
    transition(db, app, "needs_human", reason="challenge")
    assert app.needs_human_reason == "challenge"
    transition(db, app, "filling", reason="resumed")
    assert app.needs_human_reason is None


def test_never_resubmits(app_row):
    db, user, app = app_row
    transition(db, app, "queued")
    transition(db, app, "filling")
    transition(db, app, "submitting")
    transition(db, app, "submitted_unconfirmed")
    # An ambiguous submit is terminal — no path back to submitting.
    with pytest.raises(InvalidTransitionError):
        transition(db, app, "submitting")


# --- CAPTCHA / challenge detection -----------------------------------------


@pytest.mark.parametrize(
    "html",
    [
        '<script src="https://www.google.com/recaptcha/api.js"></script>',
        '<div class="h-captcha" data-sitekey="abc"></div>',
        '<iframe src="https://challenges.cloudflare.com/turnstile"></iframe>',
        "<div data-sitekey='xyz'></div>",
        "<p>Please verify you are human before continuing</p>",
        "<title>Just a moment...</title>",
        '<script src="https://client.px-cloud.net/main.js"></script>',
    ],
)
def test_challenge_detected(html):
    assert check_html(html).detected


def test_clean_page_not_flagged():
    assert not check_html("<form><input name='email'></form>").detected


def test_login_wall_detection():
    assert is_login_url("https://accounts.google.com/signin")
    assert is_login_url("https://boards.greenhouse.io/acme/login")
    assert not is_login_url("https://boards.greenhouse.io/acme/jobs/1")
    # Already on login when the flow started -> not a mid-flow wall.
    assert not is_login_url(
        "https://site/login?step=2", previous_url="https://site/login"
    )


# --- Pacing -----------------------------------------------------------------


def test_pacing_ceilings(app_row, monkeypatch):
    from app.services import pacing

    db, user, _ = app_row
    # Fabricate submissions in the last hour.
    listing_ids = []
    for i in range(20):
        li = JobListing(
            user_id=user.id, source="s", canonical_url=f"https://x/p{i}", title="t", company="c"
        )
        db.add(li)
        db.flush()
        listing_ids.append(li.id)
    from app.config import get_settings

    settings = get_settings()
    for i in range(settings.max_applications_per_hour):
        db.add(
            Application(
                user_id=user.id,
                listing_id=listing_ids[i],
                status="submitted",
                mode="auto",
                submitted_at=utcnow() - dt.timedelta(minutes=5),
            )
        )
    db.flush()
    decision = pacing.check_submission_allowance(db, user.id)
    assert decision.allowed is False
    assert "hour" in (decision.reason or "").lower()


def test_pacing_allows_when_under_ceiling(app_row):
    from app.services.pacing import check_submission_allowance

    db, user, _ = app_row
    assert check_submission_allowance(db, user.id).allowed is True
