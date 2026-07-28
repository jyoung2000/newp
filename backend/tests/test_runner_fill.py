"""Exercise the Playwright runner's orchestration with a fake session — no
real browser — to verify the fill → intervention → challenge → submit paths
and the shared resolver/state-machine wiring."""
from __future__ import annotations

import asyncio

import pytest

from app.db import get_sessionmaker
from app.executor.playwright_executor import ChallengeDetected, DetectedFormField
from app.executor.runner import process_application
from app.models import Application, JobListing, Profile, RunBatch, User, utcnow


class FakeSession:
    def __init__(self, fields, *, challenge_on_goto=False, challenge_on_field=None, confirmed=True):
        self.fields = fields
        self.challenge_on_goto = challenge_on_goto
        self.challenge_on_field = challenge_on_field
        self.confirmed = confirmed
        self.filled: dict[str, str] = {}
        self.selected: dict[str, str] = {}
        self.checked: dict[str, bool] = {}
        self.uploaded: dict[str, str] = {}
        self.submitted = False
        self.page = object()

    async def start(self):
        pass

    async def close(self):
        pass

    async def goto(self, url):
        if self.challenge_on_goto:
            raise ChallengeDetected("recaptcha on landing", "challenge")

    async def check_for_challenge(self, previous_url):
        pass

    async def discover_fields(self):
        return self.fields

    async def fill_text(self, ref, value):
        if self.challenge_on_field == ref:
            raise ChallengeDetected("challenge mid-fill", "challenge")
        self.filled[ref] = value

    async def select_option(self, ref, option_text):
        self.selected[ref] = option_text

    async def set_checkbox(self, ref, checked):
        self.checked[ref] = checked

    async def choose_radio(self, name, value):
        self.selected[name] = value

    async def upload_file(self, ref, path):
        self.uploaded[ref] = path

    async def screenshot(self):
        return b"\x89PNG\r\n\x1a\n fake"

    # Used by _submit / _snapshot / _looks_confirmed via monkeypatched helpers.


@pytest.fixture()
def db(engine):
    session = get_sessionmaker()()
    yield session
    session.rollback()
    session.close()


def _make_user(db, *, complete=True):
    user = User(email=f"runner{utcnow().timestamp()}@example.com", password_hash="x", settings={})
    db.add(user)
    db.flush()
    profile = Profile(
        user_id=user.id,
        first_name="Ada",
        last_name="Lovelace",
        email="ada@example.com",
        phone="+1 555 0100",
        authorized_countries=["United States"] if complete else [],
        requires_sponsorship=False if complete else None,
        over_18=True if complete else None,
    )
    db.add(profile)
    listing = JobListing(
        user_id=user.id, source="greenhouse",
        canonical_url="https://boards.greenhouse.io/acme/jobs/1",
        apply_url="https://boards.greenhouse.io/acme/jobs/1",
        title="Backend Engineer", company="Acme",
    )
    db.add(listing)
    batch = RunBatch(user_id=user.id, mode="auto", status="running", started_at=utcnow())
    db.add(batch)
    db.flush()
    app = Application(
        user_id=user.id, listing_id=listing.id, run_batch_id=batch.id,
        status="filling", mode="auto", executor="playwright", humanize=False,
    )
    db.add(app)
    db.flush()
    return user, app


def _patch_session(monkeypatch, fake):
    monkeypatch.setattr(
        "app.executor.runner.PlaywrightSession", lambda humanize: fake
    )


def _stub_submit(monkeypatch, fake):
    async def fake_submit(db, user, app, session):
        from app.executor.states import transition
        from app.services.pacing import check_submission_allowance

        if not check_submission_allowance(db, user.id).allowed:
            transition(db, app, "needs_human", reason="error")
            return
        transition(db, app, "submitting")
        app.confirmation_screenshot_path = "screens/confirmation.png"
        app.field_snapshot = {"jp-0": {"value": "Ada"}}
        fake.submitted = True
        transition(db, app, "submitted" if fake.confirmed else "submitted_unconfirmed")

    monkeypatch.setattr("app.executor.runner._submit", fake_submit)


def test_auto_fill_and_submit(db, monkeypatch):
    user, app = _make_user(db)
    fields = [
        DetectedFormField("jp-0", "First Name", "text", [], True, "first_name", ""),
        DetectedFormField("jp-1", "Email", "email", [], True, "email", ""),
        DetectedFormField(
            "jp-2", "Will you require sponsorship?", "radio", ["Yes", "No"], True, "sponsor", ""
        ),
    ]
    fake = FakeSession(fields)
    _patch_session(monkeypatch, fake)
    _stub_submit(monkeypatch, fake)
    asyncio.run(process_application(db, user, app))
    assert app.status == "submitted"
    assert fake.filled["jp-0"] == "Ada"
    assert fake.selected["sponsor"] == "No"
    assert fake.submitted is True


def test_unknown_field_raises_intervention(db, monkeypatch):
    user, app = _make_user(db)
    fields = [
        DetectedFormField("jp-0", "First Name", "text", [], True, "first_name", ""),
        DetectedFormField(
            "jp-1", "What is your favorite algorithm?", "text", [], True, "fav", ""
        ),
    ]
    fake = FakeSession(fields)
    _patch_session(monkeypatch, fake)
    _stub_submit(monkeypatch, fake)
    asyncio.run(process_application(db, user, app))
    assert app.status == "needs_human"
    assert app.needs_human_reason == "unknown_field"
    from app.models import Intervention

    ivs = list(db.query(Intervention).filter_by(application_id=app.id))
    assert any(i.kind == "unknown_field" for i in ivs)
    assert fake.submitted is False  # never submitted with an open question


def test_knockout_without_answer_blocks_submit(db, monkeypatch):
    # Incomplete profile: no clearance stored, form asks for it.
    user, app = _make_user(db, complete=True)
    fields = [
        DetectedFormField("jp-0", "First Name", "text", [], True, "first_name", ""),
        DetectedFormField(
            "jp-1", "Do you have an active security clearance?", "radio", ["Yes", "No"], True, "clr", ""
        ),
    ]
    fake = FakeSession(fields)
    _patch_session(monkeypatch, fake)
    _stub_submit(monkeypatch, fake)
    asyncio.run(process_application(db, user, app))
    assert app.status == "needs_human"
    assert fake.submitted is False


def test_challenge_on_landing_routes_to_human(db, monkeypatch):
    user, app = _make_user(db)
    fake = FakeSession([], challenge_on_goto=True)
    _patch_session(monkeypatch, fake)
    _stub_submit(monkeypatch, fake)
    asyncio.run(process_application(db, user, app))
    assert app.status == "needs_human"
    assert app.needs_human_reason == "challenge"
    from app.models import Intervention

    ivs = list(db.query(Intervention).filter_by(application_id=app.id))
    assert any(i.kind == "challenge" for i in ivs)
    assert fake.submitted is False


def test_challenge_mid_fill_halts_before_submit(db, monkeypatch):
    user, app = _make_user(db)
    fields = [
        DetectedFormField("jp-0", "First Name", "text", [], True, "first_name", ""),
        DetectedFormField("jp-1", "Email", "email", [], True, "email", ""),
    ]
    fake = FakeSession(fields, challenge_on_field="jp-1")
    _patch_session(monkeypatch, fake)
    _stub_submit(monkeypatch, fake)
    asyncio.run(process_application(db, user, app))
    assert app.status == "needs_human"
    assert app.needs_human_reason == "challenge"
    assert fake.submitted is False


def test_draft_mode_never_submits(db, monkeypatch):
    user, app = _make_user(db)
    app.mode = "draft"
    db.flush()
    fields = [DetectedFormField("jp-0", "First Name", "text", [], True, "first_name", "")]
    fake = FakeSession(fields)
    _patch_session(monkeypatch, fake)
    _stub_submit(monkeypatch, fake)
    asyncio.run(process_application(db, user, app))
    assert app.status == "drafted"
    assert fake.submitted is False
    assert app.confirmation_screenshot_path is not None


def test_review_mode_raises_review_intervention(db, monkeypatch):
    user, app = _make_user(db)
    app.mode = "review"
    db.flush()
    fields = [DetectedFormField("jp-0", "First Name", "text", [], True, "first_name", "")]
    fake = FakeSession(fields)
    _patch_session(monkeypatch, fake)
    _stub_submit(monkeypatch, fake)
    asyncio.run(process_application(db, user, app))
    assert app.status == "needs_human"
    from app.models import Intervention

    ivs = list(db.query(Intervention).filter_by(application_id=app.id))
    assert any(i.kind == "review" for i in ivs)
    assert fake.submitted is False


def test_stopped_run_leaves_no_submission(db, monkeypatch):
    user, app = _make_user(db)
    # Stop the run before the fill starts.
    batch = db.get(RunBatch, app.run_batch_id)
    batch.status = "stopped"
    db.flush()
    fields = [DetectedFormField("jp-0", "First Name", "text", [], True, "first_name", "")]
    fake = FakeSession(fields)
    _patch_session(monkeypatch, fake)
    _stub_submit(monkeypatch, fake)
    asyncio.run(process_application(db, user, app))
    assert app.status == "stopped"
    assert fake.submitted is False
