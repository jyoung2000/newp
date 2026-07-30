"""Roles the user wants, and the gate that keeps their list on target."""
from __future__ import annotations

from tests.conftest import register_and_login


def test_preview_shows_the_variations_before_anything_is_saved(client):
    headers = register_and_login(client, "prev@example.com")
    r = client.get("/api/roles/preview?title=Software%20Engineer", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["title"] == "Software Engineer"
    assert body["recognised"] is True
    lowered = [v.lower() for v in body["variations"]]
    assert "software developer" in lowered
    # The title itself isn't repeated back as one of its own variations.
    assert "software engineer" not in lowered
    # Nothing was created.
    assert client.get("/api/roles", headers=headers).json() == []


def test_preview_says_when_a_title_is_not_recognised(client):
    headers = register_and_login(client, "unknown@example.com")
    body = client.get("/api/roles/preview?title=Sommelier", headers=headers).json()
    assert body["recognised"] is False
    assert body["variations"] == []


def test_a_role_becomes_a_scheduled_target(client, engine):
    """The point of the wrapper: a saved role is picked up by the scheduler
    that already exists, with no further setup."""
    from sqlalchemy import select
    from sqlalchemy.orm import Session

    from app.models import SearchTarget

    headers = register_and_login(client, "sched@example.com")
    r = client.post("/api/roles", json={"title": "Software Engineer"}, headers=headers)
    assert r.status_code == 201, r.text
    role = r.json()
    assert role["title"] == "Software Engineer"
    assert role["schedule_minutes"] == 180
    assert role["listings_found"] == 0
    assert any("developer" in v.lower() for v in role["variations"])

    with Session(engine) as db:
        target = db.scalars(select(SearchTarget)).one()
        assert target.name == "Software Engineer"
        # The user's own wording always leads the terms.
        assert target.title_terms[0] == "Software Engineer"
        assert target.schedule_minutes == 180
        assert target.notify_new is True
        # Empty sources means "every configured source".
        assert target.sources == []


def test_the_users_own_wording_survives_edited_variations(client):
    headers = register_and_login(client, "edit@example.com")
    created = client.post(
        "/api/roles",
        json={"title": "Widget Wrangler", "variations": ["Widget Handler"]},
        headers=headers,
    ).json()
    assert created["variations"] == ["Widget Handler"]

    r = client.put(
        f"/api/roles/{created['id']}",
        json={"title": "Widget Wrangler", "variations": []},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    # An explicitly empty list is an answer, not a request to re-propose.
    assert r.json()["variations"] == []


def test_roles_can_be_listed_edited_and_deleted(client):
    headers = register_and_login(client, "crud@example.com")
    a = client.post("/api/roles", json={"title": "Data Analyst"}, headers=headers).json()
    client.post("/api/roles", json={"title": "Product Manager"}, headers=headers)
    assert [x["title"] for x in client.get("/api/roles", headers=headers).json()] == [
        "Data Analyst",
        "Product Manager",
    ]

    r = client.put(
        f"/api/roles/{a['id']}",
        json={"title": "Senior Data Analyst", "location": "Remote", "remote": True,
              "schedule_minutes": 360},
        headers=headers,
    )
    assert r.status_code == 200
    assert r.json()["title"] == "Senior Data Analyst"
    assert r.json()["schedule_minutes"] == 360

    assert client.delete(f"/api/roles/{a['id']}", headers=headers).status_code == 200
    assert [x["title"] for x in client.get("/api/roles", headers=headers).json()] == [
        "Product Manager"
    ]


def test_duplicate_roles_are_refused(client):
    headers = register_and_login(client, "dup@example.com")
    client.post("/api/roles", json={"title": "Software Engineer"}, headers=headers)
    r = client.post("/api/roles", json={"title": "software engineer"}, headers=headers)
    assert r.status_code == 409
    assert "already have a role" in r.json()["detail"]


def test_one_users_roles_are_invisible_to_another(client):
    a = register_and_login(client, "a@example.com")
    client.post("/api/roles", json={"title": "Software Engineer"}, headers=a)
    b = register_and_login(client, "b@example.com")
    assert client.get("/api/roles", headers=b).json() == []
    # And cannot be reached by id.
    assert client.delete("/api/roles/1", headers=b).status_code == 404
    assert client.put("/api/roles/1", json={"title": "Mine now"}, headers=b).status_code == 404


def test_roles_require_authentication(client):
    assert client.get("/api/roles").status_code == 401
    assert client.post("/api/roles", json={"title": "X"}).status_code in (401, 403)


# --- The gate ---------------------------------------------------------------


def test_the_gate_keeps_variations_and_drops_other_jobs(client):
    """A board connector returning an employer's whole job list is the case
    that makes this necessary."""
    from app.services.search_service import _gate_titles
    from app.sources.base import RawListing

    def listing(title):
        return RawListing(source="test", url=f"https://x/{title}", title=title, company="Acme")

    raw = [
        listing("Software Engineer"),
        listing("Senior Software Developer"),
        listing("Backend Engineer"),
        listing("Engineering Manager"),
        listing("Sales Engineer"),
        listing("Truck Driver"),
        listing("Marketing Coordinator"),
    ]
    kept, rejected = _gate_titles(raw, ["Software Engineer"])
    assert [x.title for x in kept] == [
        "Software Engineer",
        "Senior Software Developer",
        "Backend Engineer",
    ]
    assert rejected == 4


def test_no_gate_without_role_titles(client):
    """An ad-hoc keyword search ("python", "remote") is not a title search, and
    gating it would reject everything."""
    from app.services.search_service import _gate_titles
    from app.sources.base import RawListing

    raw = [RawListing(source="t", url="https://x/1", title="Backend Engineer", company="Acme")]
    kept, rejected = _gate_titles(raw, None)
    assert kept == raw and rejected == 0
    kept, rejected = _gate_titles(raw, [])
    assert kept == raw and rejected == 0


def test_listings_record_which_role_they_answered(client, engine):
    from sqlalchemy.orm import Session

    from app.models import JobListing, User
    from app.services.search_service import _stamp_matched_role

    register_and_login(client, "stamp@example.com")
    with Session(engine) as db:
        from sqlalchemy import select

        user = db.scalars(select(User)).first()
        rows = [
            JobListing(user_id=user.id, source="t", canonical_url="https://x/1",
                       title="Senior Software Developer", company="Acme"),
            JobListing(user_id=user.id, source="t", canonical_url="https://x/2",
                       title="Data Analyst", company="Acme"),
        ]
        _stamp_matched_role(rows, ["Software Engineer", "Data Analyst"])
        assert rows[0].matched_role == "Software Engineer"
        assert rows[1].matched_role == "Data Analyst"


def test_listings_found_counts_what_arrived_for_a_role(client, engine):
    from sqlalchemy import select
    from sqlalchemy.orm import Session

    from app.models import JobListing, User

    headers = register_and_login(client, "count@example.com")
    role = client.post("/api/roles", json={"title": "Software Engineer"}, headers=headers).json()
    with Session(engine) as db:
        user = db.scalars(select(User)).first()
        for i in range(3):
            db.add(
                JobListing(
                    user_id=user.id, source="t", canonical_url=f"https://x/{i}",
                    title="Software Engineer", company="Acme",
                    matched_role="Software Engineer",
                )
            )
        db.add(
            JobListing(user_id=user.id, source="t", canonical_url="https://x/other",
                       title="Data Analyst", company="Acme", matched_role="Data Analyst")
        )
        db.commit()

    fetched = client.get("/api/roles", headers=headers).json()
    assert fetched[0]["id"] == role["id"]
    assert fetched[0]["listings_found"] == 3
