from __future__ import annotations

import pytest

from app.services.ingest import canonicalize_url
from app.services.salary import parse_salary


@pytest.mark.parametrize(
    "text,minimum,maximum,currency,period",
    [
        ("$120,000 - $150,000 per year", 120000, 150000, "USD", "year"),
        ("£45k", 45000, 45000, "GBP", "year"),
        ("€60.000 jährlich per year", 60000, 60000, "EUR", "year"),
        ("$18.50/hr", 18, 18, "USD", "hour"),
        ("45 - 55 per hour", 45, 55, None, "hour"),
        ("USD 100000", 100000, 100000, "USD", "year"),
        ("Up to $90k per year", None, 90000, "USD", "year"),
        ("185K – 230K", 185000, 230000, None, "year"),
        ("₹1,200,000 per annum", 1200000, 1200000, "INR", "year"),
        ("8,000 per month", 8000, 8000, None, "month"),
    ],
)
def test_salary_parsing(text, minimum, maximum, currency, period):
    parsed = parse_salary(text)
    assert parsed.minimum == minimum
    assert parsed.maximum == maximum
    assert parsed.currency == currency
    assert parsed.period == period


@pytest.mark.parametrize("text", [None, "", "Not listed", "Competitive salary", "DOE"])
def test_salary_not_listed(text):
    parsed = parse_salary(text)
    assert not parsed.listed


def test_canonicalize_strips_tracking():
    a = canonicalize_url(
        "https://boards.greenhouse.io/Acme/jobs/123?gh_src=abc&utm_source=x&gh_jid=123#apply"
    )
    b = canonicalize_url("https://boards.greenhouse.io/acme/jobs/123/?gh_jid=123")
    assert a == b
    assert "utm" not in a and "gh_src" not in a
    assert "gh_jid=123" in a  # posting id preserved


def test_canonicalize_preserves_distinct_ids():
    a = canonicalize_url("https://example.com/careers?job_id=1")
    b = canonicalize_url("https://example.com/careers?job_id=2")
    assert a != b


def test_upsert_dedupes(engine):
    from app.db import get_sessionmaker
    from app.models import Profile, User
    from app.services.ingest import upsert_listings
    from app.sources.base import RawListing

    db = get_sessionmaker()()
    user = User(email="dedupe@example.com", password_hash="x", settings={})
    db.add(user)
    db.flush()
    db.add(Profile(user_id=user.id))
    db.commit()

    listing = RawListing(
        source="greenhouse",
        url="https://boards.greenhouse.io/acme/jobs/1?gh_src=z",
        title="Backend Engineer",
        company="Acme",
    )
    new_rows, dupes = upsert_listings(db, user, [listing])
    assert len(new_rows) == 1 and dupes == 0

    # Same URL modulo tracking params -> dupe.
    again = RawListing(
        source="greenhouse",
        url="https://boards.greenhouse.io/ACME/jobs/1/",
        title="Backend Engineer",
        company="Acme",
    )
    new_rows, dupes = upsert_listings(db, user, [again])
    assert len(new_rows) == 0 and dupes == 1

    # Same title+company via a different URL (aggregator copy) -> fuzzy dupe.
    aggregator_copy = RawListing(
        source="adzuna",
        url="https://adzuna.example/redirect/xyz",
        title="Backend Engineer",
        company="Acme",
    )
    new_rows, dupes = upsert_listings(db, user, [aggregator_copy])
    assert len(new_rows) == 0 and dupes == 1

    # A genuinely different role is kept.
    other = RawListing(
        source="adzuna",
        url="https://adzuna.example/redirect/abc",
        title="Staff Platform Engineer",
        company="Acme",
    )
    new_rows, dupes = upsert_listings(db, user, [other])
    assert len(new_rows) == 1
    db.close()
