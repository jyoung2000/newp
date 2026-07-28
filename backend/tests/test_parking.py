"""§2 point 6: an unanswered intervention parks the job as needs_human
(waiting) after the window; the runner moves on and NEVER times out into an
automatic attempt."""
from __future__ import annotations

import datetime as dt

import pytest

from app.db import get_sessionmaker
from app.executor.runner import (
    claim_next_playwright_job,
    park_expired_interventions,
    resumable_playwright_job,
)
from app.models import (
    Application,
    Intervention,
    JobListing,
    Profile,
    RunBatch,
    User,
    utcnow,
)


@pytest.fixture()
def db(engine):
    s = get_sessionmaker()()
    yield s
    s.rollback()
    s.close()


def _setup(db):
    user = User(email="park@example.com", password_hash="x", settings={})
    db.add(user)
    db.flush()
    db.add(Profile(user_id=user.id))
    listing = JobListing(
        user_id=user.id, source="s", canonical_url="https://x/1", title="T", company="C"
    )
    db.add(listing)
    batch = RunBatch(user_id=user.id, mode="auto", status="running", started_at=utcnow())
    db.add(batch)
    db.flush()
    app = Application(
        user_id=user.id, listing_id=listing.id, run_batch_id=batch.id,
        status="needs_human", mode="auto", executor="playwright", needs_human_reason="unknown_field",
    )
    db.add(app)
    db.flush()
    return user, app


def test_fresh_intervention_not_parked(db):
    user, app = _setup(db)
    db.add(
        Intervention(
            application_id=app.id, user_id=user.id, kind="unknown_field",
            question="Q", status="open", created_at=utcnow(),
        )
    )
    db.flush()
    assert park_expired_interventions(db) == 0
    assert app.parked_at is None


def test_expired_intervention_parks_and_runner_moves_on(db):
    user, app = _setup(db)
    # An intervention older than the wait window.
    db.add(
        Intervention(
            application_id=app.id, user_id=user.id, kind="unknown_field",
            question="Q", status="open",
            created_at=utcnow() - dt.timedelta(minutes=45),
        )
    )
    db.flush()

    parked = park_expired_interventions(db)
    assert parked == 1
    assert app.parked_at is not None
    # Crucially: parking is a status timestamp, NOT a transition to submitting.
    # The application stays needs_human — never an automatic attempt.
    assert app.status == "needs_human"

    # A parked job is not offered back to the runner as resumable...
    assert resumable_playwright_job(db, user.id) is None
    # ...and there's no fresh queued work, so the runner simply moves on.
    assert claim_next_playwright_job(db, user.id) is None

    events = [e.type for e in app.events]
    assert "parked" in events


def test_answered_intervention_makes_job_resumable_not_parked(db):
    user, app = _setup(db)
    iv = Intervention(
        application_id=app.id, user_id=user.id, kind="unknown_field",
        question="Q", status="answered",
        created_at=utcnow() - dt.timedelta(minutes=45),
    )
    db.add(iv)
    db.flush()
    # No OPEN interventions remain -> not parked, and it IS resumable.
    assert park_expired_interventions(db) == 0
    assert app.parked_at is None
    assert resumable_playwright_job(db, user.id) is not None
