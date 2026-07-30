"""Seed a demo user with a profile and real listings, so first run isn't empty.

Tries live Greenhouse/Lever boards first; on any network failure it falls
back to bundled fixtures and says which it used. Idempotent: re-running
updates the demo user rather than duplicating it.

    python -m app.seed
"""
from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import select

from app.db import get_sessionmaker
from app.logging_conf import configure_logging, get_logger
from app.models import Base, JobListing, Profile, User
from app.security import hash_password
from app.services.ingest import enrich_listings, upsert_listings
from app.sources.ats_boards import GreenhouseSource, LeverSource
from app.sources.base import OrgRef, SearchQuery
from app.sources.http import get_http

log = get_logger(__name__)

DEMO_EMAIL = "demo@jobpilot.local"
DEMO_PASSWORD = "demo-password-1234"

# Real, public boards used for the live seed.
SEED_ORGS = [
    OrgRef("greenhouse", "stripe", "Stripe"),
    OrgRef("greenhouse", "airbnb", "Airbnb"),
    OrgRef("lever", "netflix", "Netflix"),
]

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures"


def _ensure_demo_user(db) -> User:
    user = db.scalar(select(User).where(User.email == DEMO_EMAIL))
    if user is None:
        user = User(
            email=DEMO_EMAIL,
            password_hash=hash_password(DEMO_PASSWORD),
            settings={"humanize_default": True, "run_mode_default": "review"},
            # Never the head admin. This account is created unattended with a
            # password printed in the installer output and the README, so the
            # role would be handed to anyone who can read either.
            is_admin=False,
        )
        db.add(user)
        db.flush()
    profile = db.scalar(select(Profile).where(Profile.user_id == user.id))
    if profile is None:
        profile = Profile(user_id=user.id)
        db.add(profile)
    profile.first_name = "Demo"
    profile.last_name = "Candidate"
    profile.email = DEMO_EMAIL
    profile.phone = "+1 555 0100"
    profile.city = "San Francisco"
    profile.state = "CA"
    profile.country = "United States"
    profile.authorized_countries = ["United States"]
    profile.requires_sponsorship = False
    profile.work_model_preference = "remote"
    profile.willing_to_relocate = False
    profile.salary_expectation_amount = 165000
    profile.salary_expectation_currency = "USD"
    profile.salary_expectation_period = "year"
    profile.total_years_experience = 6
    profile.how_heard_default = "Company careers page"
    profile.over_18 = True
    profile.skills_years = {
        "Python": {"years": 6, "confirmed": True},
        "TypeScript": {"years": 4, "confirmed": True},
        "PostgreSQL": {"years": 5, "confirmed": True},
    }
    db.flush()
    return user


def _live_listings(query: SearchQuery) -> tuple[list, str]:
    http = get_http()
    listings = []
    used = "live"
    try:
        listings += GreenhouseSource().search(query, http, SEED_ORGS)
        listings += LeverSource().search(query, http, SEED_ORGS)
    except Exception as exc:
        log.info("seed.live_failed", error=str(exc))
    if not listings:
        used = "fixtures"
        listings = _fixture_listings()
    return listings, used


def _fixture_listings() -> list:
    from app.sources.ats_boards import (
        AshbySource,
        GreenhouseSource,
        LeverSource,
        WorkableSource,
    )

    class _FakeResponse:
        def __init__(self, data):
            self._data = data
            self.status_code = 200

        def json(self):
            return self._data

    class _FakeHttp:
        def __init__(self, mapping):
            self._mapping = mapping

        def get(self, url, **_kwargs):
            for needle, data in self._mapping.items():
                if needle in url:
                    return _FakeResponse(data)
            return _FakeResponse({})

    gh = json.loads((FIXTURES / "greenhouse_jobs.json").read_text())
    lv = json.loads((FIXTURES / "lever_postings.json").read_text())
    ash = json.loads((FIXTURES / "ashby_board.json").read_text())
    wk = json.loads((FIXTURES / "workable_widget.json").read_text())
    http = _FakeHttp({"greenhouse": gh, "lever": lv, "ashby": ash, "workable": wk})
    query = SearchQuery(terms=[])
    listings = []
    listings += GreenhouseSource().org_listings(OrgRef("greenhouse", "acmecorp", "Acme Corp"), http, query)  # type: ignore[arg-type]
    listings += LeverSource().org_listings(OrgRef("lever", "globex", "Globex"), http, query)  # type: ignore[arg-type]
    listings += AshbySource().org_listings(OrgRef("ashby", "initech", "Initech"), http, query)  # type: ignore[arg-type]
    listings += WorkableSource().org_listings(OrgRef("workable", "hooli", "Hooli"), http, query)  # type: ignore[arg-type]
    return listings


def seed() -> None:
    configure_logging()
    from app.db import get_engine

    Base.metadata.create_all(get_engine())  # safety for fresh volumes pre-migration
    db = get_sessionmaker()()
    try:
        user = _ensure_demo_user(db)
        existing = db.scalar(select(JobListing).where(JobListing.user_id == user.id))
        if existing is not None:
            db.commit()
            log.info("seed.already_seeded", email=DEMO_EMAIL)
            print(f"Demo user {DEMO_EMAIL} already has listings; profile refreshed.")
            return
        query = SearchQuery(
            terms=["engineer", "python", "developer", "designer", "backend", "software"],
            posted_within_days=90,
        )
        raw, used = _live_listings(query)
        new_rows, _ = upsert_listings(db, user, raw[:25])
        enrich_listings(db, user, new_rows, limit=25)
        db.commit()
        log.info("seed.done", listings=len(new_rows), source=used)
        print(
            f"Seeded demo user {DEMO_EMAIL} (password: {DEMO_PASSWORD}) "
            f"with {len(new_rows)} listings from {used} data."
        )
    finally:
        db.close()


if __name__ == "__main__":
    seed()
