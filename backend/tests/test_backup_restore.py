"""Backing up an account and putting it back.

The individual exports were already covered; what wasn't is the round trip —
export everything, restore it into a different account, and check the things a
person would actually miss: their profile, their work history, their custom
answers, their job list, their application outcomes and their résumé bytes.
"""
from __future__ import annotations

import io
import json
import zipfile

from tests.conftest import register_and_login

RESUME = b"Ada Lovelace\nada@example.com\nAnalytical Engine, 1843"


def rows(payload):
    """List endpoints return a bare list; paginated ones wrap in {"items": …}."""
    return payload["items"] if isinstance(payload, dict) else payload


def _fill_account(client, headers) -> dict:
    """Give an account the kind of data a real user would have entered."""
    client.put(
        "/api/profile",
        json={
            "first_name": "Ada",
            "last_name": "Lovelace",
            "email": "ada@example.com",
            "phone": "+1 555 0100",
            "city": "London",
            "country": "United Kingdom",
            "authorized_countries": ["United States", "United Kingdom"],
            "requires_sponsorship": False,
            "over_18": True,
            "total_years_experience": 6,
            "how_heard_default": "Careers page",
            "skills_years": {"Python": {"years": 6, "confirmed": True}},
        },
        headers=headers,
    )
    r = client.post(
        "/api/profile/work-experiences",
        json={
            "title": "Staff Engineer",
            "company": "Analytical Engines Ltd",
            "location": "London",
            "is_current": True,
            "bullets": ["Wrote the first program"],
        },
        headers=headers,
    )
    assert r.status_code in (200, 201), r.text
    r = client.post(
        "/api/custom-fields",
        json={"label": "Preferred pronoun", "key": "pronoun", "type": "text", "value": "she/her"},
        headers=headers,
    )
    assert r.status_code in (200, 201), r.text
    r = client.post(
        "/api/saved-answers",
        json={"question_text": "Why this company?", "answer": "Because of the engine."},
        headers=headers,
    )
    assert r.status_code in (200, 201), r.text
    r = client.post(
        "/api/files",
        files={"file": ("resume.txt", io.BytesIO(RESUME), "text/plain")},
        data={"kind": "resume"},
        headers=headers,
    )
    assert r.status_code in (200, 201), r.text
    listing = client.post(
        "/api/listings/manual",
        json={
            "title": "Backend Engineer",
            "company": "Acme",
            "apply_url": "https://acme.example/jobs/42",
            "location": "Remote",
        },
        headers=headers,
    ).json()
    # An application with an outcome the user recorded themselves — the part
    # that used to be export-only.
    run = client.post(
        "/api/runs",
        json={"listing_ids": [listing["id"]], "mode": "review", "executor": "extension"},
        headers=headers,
    ).json()
    app_id = rows(client.get("/api/applications", headers=headers).json())[0]["id"]
    r = client.post(
        f"/api/applications/{app_id}/outcome",
        json={"outcome": "interview"},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    return {"listing": listing, "run": run, "application_id": app_id}


def _export(client, headers) -> bytes:
    r = client.get("/api/transfer/everything.zip", headers=headers)
    assert r.status_code == 200, r.text
    return r.content


def test_the_backup_contains_everything_a_restore_needs(client):
    headers = register_and_login(client, "owner@example.com")
    _fill_account(client, headers)
    zf = zipfile.ZipFile(io.BytesIO(_export(client, headers)))
    names = set(zf.namelist())

    # The human-readable exports stay exactly as they were.
    for legacy in ("profile.json", "listings.csv", "listings.json", "applications.csv"):
        assert legacy in names, legacy
    # And the machine-readable halves a restore actually reads.
    for needed in ("manifest.json", "applications.json", "files.json"):
        assert needed in names, needed

    manifest = json.loads(zf.read("manifest.json"))
    assert manifest["jobpilot_backup_version"] == 1
    assert manifest["account_email"] == "owner@example.com"
    assert manifest["counts"]["listings"] == 1
    assert manifest["counts"]["applications"] == 1
    assert manifest["counts"]["files"] == 1

    # The résumé bytes are in there, not just its name.
    entry = json.loads(zf.read("files.json"))[0]["entry"]
    assert zf.read(entry) == RESUME


def test_preview_describes_the_archive_without_changing_anything(client):
    headers = register_and_login(client, "prev@example.com")
    _fill_account(client, headers)
    backup = _export(client, headers)

    other = register_and_login(client, "prev-target@example.com")
    r = client.post(
        "/api/transfer/backup/preview",
        files={"file": ("jobpilot-export.zip", io.BytesIO(backup), "application/zip")},
        headers=other,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["valid"] is True
    assert body["account_email"] == "prev@example.com"
    assert body["listings"] == 1
    assert body["applications"] == 1
    assert body["files"] == 1
    assert body["work_experiences"] == 1
    # Nothing landed in the target account.
    assert body["existing_listings"] == 0
    assert rows(client.get("/api/listings", headers=other).json()) == []


def test_restore_into_a_fresh_account_round_trips(client):
    headers = register_and_login(client, "from@example.com")
    _fill_account(client, headers)
    backup = _export(client, headers)
    original_profile = client.get("/api/profile", headers=headers).json()

    target = register_and_login(client, "to@example.com")
    r = client.post(
        "/api/transfer/backup/restore",
        files={"file": ("jobpilot-export.zip", io.BytesIO(backup), "application/zip")},
        headers=target,
    )
    assert r.status_code == 200, r.text
    result = r.json()
    assert result["profile_updated"] is True
    assert result["listings_imported"] == 1
    assert result["applications_imported"] == 1
    assert result["files_imported"] == 1

    # Profile and work history came back.
    restored = client.get("/api/profile", headers=target).json()
    assert restored["profile"]["first_name"] == "Ada"
    assert restored["profile"]["total_years_experience"] == 6
    assert restored["profile"]["skills_years"]["Python"]["years"] == 6
    assert len(restored["work_experiences"]) == len(original_profile["work_experiences"]) == 1
    assert restored["work_experiences"][0]["company"] == "Analytical Engines Ltd"

    # The things the user typed by hand.
    assert [c["value"] for c in client.get("/api/custom-fields", headers=target).json()] == ["she/her"]
    answers = client.get("/api/saved-answers", headers=target).json()
    assert any(a["answer"] == "Because of the engine." for a in answers)

    # The job list.
    listings = rows(client.get("/api/listings", headers=target).json())
    assert [li["title"] for li in listings] == ["Backend Engineer"]

    # The application history, with the outcome the user recorded, attached to
    # the right listing rather than orphaned.
    items = rows(client.get("/api/applications", headers=target).json())
    assert len(items) == 1
    assert items[0]["outcome"] == "interview"
    assert items[0]["title"] == "Backend Engineer"

    # The résumé, byte for byte, and still the default.
    files = client.get("/api/files", headers=target).json()
    assert len(files) == 1
    assert files[0]["filename"] == "resume.txt"
    assert files[0]["is_default_resume"] is True
    got = client.get(f"/api/files/{files[0]['id']}/download", headers=target)
    assert got.status_code == 200
    assert got.content == RESUME


def test_restoring_twice_does_not_duplicate_anything(client):
    """A restore is the kind of thing people run twice when they're unsure it
    worked. It must be idempotent, not additive."""
    headers = register_and_login(client, "twice@example.com")
    _fill_account(client, headers)
    backup = _export(client, headers)

    target = register_and_login(client, "twice-target@example.com")
    payload = {"file": ("b.zip", io.BytesIO(backup), "application/zip")}
    first = client.post("/api/transfer/backup/restore", files=payload, headers=target).json()
    second = client.post(
        "/api/transfer/backup/restore",
        files={"file": ("b.zip", io.BytesIO(backup), "application/zip")},
        headers=target,
    ).json()

    assert first["applications_imported"] == 1
    assert second["applications_imported"] == 0
    assert second["applications_skipped"] == 1
    assert second["files_imported"] == 0
    assert second["listings_imported"] == 0

    assert len(rows(client.get("/api/listings", headers=target).json())) == 1
    assert len(client.get("/api/files", headers=target).json()) == 1
    assert len(rows(client.get("/api/applications", headers=target).json())) == 1


def test_application_history_survives_a_backup_with_no_listings_file(client):
    """Older exports had no applications.json/listings.json pairing to rely on.
    An application whose listing isn't in the archive should still come back,
    attached to a recreated listing, rather than being dropped."""
    headers = register_and_login(client, "old@example.com")
    _fill_account(client, headers)
    original = zipfile.ZipFile(io.BytesIO(_export(client, headers)))

    trimmed = io.BytesIO()
    with zipfile.ZipFile(trimmed, "w") as out:
        for name in original.namelist():
            if name in ("listings.json", "listings.csv"):
                continue
            out.writestr(name, original.read(name))
    trimmed.seek(0)

    target = register_and_login(client, "old-target@example.com")
    r = client.post(
        "/api/transfer/backup/restore",
        files={"file": ("b.zip", trimmed, "application/zip")},
        headers=target,
    )
    assert r.status_code == 200, r.text
    assert r.json()["applications_imported"] == 1
    items = rows(client.get("/api/applications", headers=target).json())
    assert items[0]["outcome"] == "interview"
    assert items[0]["title"] == "Backend Engineer"


def test_a_zip_that_is_not_a_backup_is_refused_clearly(client):
    headers = register_and_login(client, "junk@example.com")
    junk = io.BytesIO()
    with zipfile.ZipFile(junk, "w") as zf:
        zf.writestr("holiday-photo.jpg", b"not a backup")
    junk.seek(0)

    r = client.post(
        "/api/transfer/backup/preview",
        files={"file": ("x.zip", junk, "application/zip")},
        headers=headers,
    )
    assert r.status_code == 200
    assert r.json()["valid"] is False
    assert "JobPilot backup" in r.json()["problem"]

    junk.seek(0)
    r = client.post(
        "/api/transfer/backup/restore",
        files={"file": ("x.zip", junk, "application/zip")},
        headers=headers,
    )
    assert r.status_code == 400


def test_a_file_that_is_not_a_zip_is_refused(client):
    headers = register_and_login(client, "notzip@example.com")
    r = client.post(
        "/api/transfer/backup/preview",
        files={"file": ("notes.txt", io.BytesIO(b"hello"), "text/plain")},
        headers=headers,
    )
    assert r.status_code == 200
    assert r.json()["valid"] is False
    assert "zip" in r.json()["problem"].lower()


def test_restore_requires_authentication(client):
    r = client.post(
        "/api/transfer/backup/restore",
        files={"file": ("b.zip", io.BytesIO(b"x"), "application/zip")},
    )
    assert r.status_code in (401, 403)


def test_one_accounts_backup_cannot_be_read_into_another_without_uploading_it(client):
    """Restore only ever acts on the bytes the caller uploads — there is no
    endpoint that reaches into someone else's export."""
    a = register_and_login(client, "a@example.com")
    _fill_account(client, a)
    b = register_and_login(client, "b@example.com")
    # B's own export is empty of A's data.
    zf = zipfile.ZipFile(io.BytesIO(_export(client, b)))
    assert json.loads(zf.read("listings.json")) == []
    assert json.loads(zf.read("applications.json")) == []
    assert json.loads(zf.read("manifest.json"))["account_email"] == "b@example.com"
