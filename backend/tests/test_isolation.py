"""Cross-user isolation: prove user A cannot read, update, or delete anything
belonging to user B, across every resource-bearing endpoint."""
from __future__ import annotations

import io

import pytest

from tests.conftest import register_and_login


@pytest.fixture()
def two_users(client):
    a = register_and_login(client, "iso-a@example.com")
    # Build a full set of A's resources while A is the active session.
    work = client.post(
        "/api/profile/work-experiences",
        json={"title": "Engineer", "company": "Acme"},
        headers=a,
    ).json()
    education = client.post(
        "/api/profile/educations", json={"school": "MIT"}, headers=a
    ).json()
    rec = client.post(
        "/api/profile/recommendations", json={"name": "Grace Hopper"}, headers=a
    ).json()
    cf = client.post(
        "/api/custom-fields", json={"label": "Badge size", "type": "text", "value": "M"}, headers=a
    ).json()
    sa = client.post(
        "/api/saved-answers", json={"question_text": "Q?", "answer": "A"}, headers=a
    ).json()
    file = client.post(
        "/api/files",
        files={"file": ("r.txt", io.BytesIO(b"Ada\nada@x.com"), "text/plain")},
        data={"kind": "resume"},
        headers=a,
    ).json()
    listing = client.post(
        "/api/listings/manual",
        json={"title": "Dev", "company": "Acme"},
        headers=a,
    ).json()
    target = client.post(
        "/api/search/targets", json={"name": "T", "title_terms": ["dev"]}, headers=a
    ).json()
    run = client.post(
        "/api/runs", json={"listing_ids": [listing["id"]], "mode": "draft"}, headers=a
    ).json()
    device_code = client.post("/api/devices/pairing-code", headers=a).json()["code"]
    device = client.post(
        "/api/ext/pair", json={"code": device_code, "name": "Laptop", "browser": "chrome"}
    ).json()
    app_list = client.get("/api/applications", headers=a).json()
    a_ids = {
        "work": work["id"],
        "education": education["id"],
        "recommendation": rec["id"],
        "custom_field": cf["id"],
        "saved_answer": sa["id"],
        "file": file["id"],
        "listing": listing["id"],
        "target": target["id"],
        "run": run["run"]["id"],
        "device": device["device_id"],
        "application": app_list[0]["id"] if app_list else None,
    }
    # Now switch to user B (cookie jar replaced).
    b = register_and_login(client, "iso-b@example.com")
    return a, b, a_ids


def test_b_cannot_read_a_resources(client, two_users):
    _a, _b, ids = two_users
    reads = [
        f"/api/files/{ids['file']}/download",
        f"/api/listings/{ids['listing']}",
        f"/api/applications/{ids['application']}",
        f"/api/runs/{ids['run']}",
    ]
    for url in reads:
        assert client.get(url).status_code == 404, url

    # List endpoints must return only B's (empty) resources, never A's.
    assert client.get("/api/listings").json() == []
    assert client.get("/api/applications").json() == []
    assert client.get("/api/custom-fields").json() == []
    assert client.get("/api/saved-answers").json() == []
    assert client.get("/api/search/targets").json() == []
    assert client.get("/api/devices").json() == []
    assert client.get("/api/profile").json()["work_experiences"] == []


def test_b_cannot_update_a_resources(client, two_users):
    _a, b, ids = two_users
    updates = [
        ("put", f"/api/profile/work-experiences/{ids['work']}", {"title": "X", "company": "Y"}),
        ("put", f"/api/profile/educations/{ids['education']}", {"school": "Hacked"}),
        ("put", f"/api/profile/recommendations/{ids['recommendation']}", {"name": "Mallory"}),
        ("put", f"/api/custom-fields/{ids['custom_field']}", {"label": "x", "type": "text", "value": "z"}),
        ("put", f"/api/saved-answers/{ids['saved_answer']}", {"question_text": "Q?", "answer": "hacked"}),
        ("put", f"/api/search/targets/{ids['target']}", {"name": "x", "title_terms": ["z"]}),
        ("post", f"/api/files/{ids['file']}/default-resume", None),
        ("post", f"/api/applications/{ids['application']}/skip", None),
        ("post", f"/api/runs/{ids['run']}/stop", None),
    ]
    for method, url, body in updates:
        fn = getattr(client, method)
        resp = fn(url, json=body, headers=b) if body is not None else fn(url, headers=b)
        assert resp.status_code == 404, f"{method} {url} -> {resp.status_code}"


def test_b_cannot_delete_a_resources(client, two_users):
    _a, b, ids = two_users
    deletes = [
        f"/api/profile/work-experiences/{ids['work']}",
        f"/api/profile/educations/{ids['education']}",
        f"/api/profile/recommendations/{ids['recommendation']}",
        f"/api/custom-fields/{ids['custom_field']}",
        f"/api/saved-answers/{ids['saved_answer']}",
        f"/api/files/{ids['file']}",
        f"/api/listings/{ids['listing']}",
        f"/api/search/targets/{ids['target']}",
        f"/api/devices/{ids['device']}",
    ]
    for url in deletes:
        assert client.delete(url, headers=b).status_code == 404, url


def test_a_resources_survive_b_attempts(client, two_users):
    _a, _b, ids = two_users
    # Re-authenticate as A (the fixture left B's session cookie active).
    register_and_login  # noqa: B018 - documents dependency
    client.post(
        "/api/auth/login", json={"email": "iso-a@example.com", "password": "correct horse 9!"}
    )
    assert client.get(f"/api/listings/{ids['listing']}").status_code == 200
    assert len(client.get("/api/profile").json()["work_experiences"]) == 1
    assert client.get("/api/devices").json()[0]["id"] == ids["device"]
