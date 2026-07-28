from __future__ import annotations

import io

from tests.conftest import register_and_login

RESUME_TXT = """Ada Lovelace
London, United Kingdom
ada@example.com | +44 20 5550 0100 | https://github.com/ada

Engineer @ Analytical Engines Ltd (2019-03 - present)
- Built the difference engine pipeline

Skills: Python (4 yrs), Mathematics, Analysis
B.S. Mathematics, University of London
"""


def _upload(client, headers, filename="resume.txt", kind="resume", content=RESUME_TXT):
    return client.post(
        "/api/files",
        files={"file": (filename, io.BytesIO(content.encode()), "text/plain")},
        data={"kind": kind},
        headers=headers,
    )


def test_upload_parse_confirm_flow(client):
    headers = register_and_login(client, "f1@example.com")
    r = _upload(client, headers)
    assert r.status_code == 201, r.text
    body = r.json()
    file_id = body["id"]
    assert body["is_default_resume"] is True  # first resume becomes default
    assert body["has_text"] is True

    # Parse produces an UNCONFIRMED result for review.
    r = client.post(f"/api/files/{file_id}/parse", headers=headers)
    assert r.status_code == 200, r.text
    parsed = r.json()
    assert parsed["contact"]["email"] == "ada@example.com"
    assert client.get("/api/files").json()[0]["parse_confirmed"] is False

    # User corrects a value, then confirms.
    parsed["contact"]["first_name"] = "Augusta"
    r = client.post(
        f"/api/files/{file_id}/confirm-parse", json={"parsed": parsed}, headers=headers
    )
    assert r.status_code == 200
    profile = client.get("/api/profile").json()
    assert profile["profile"]["first_name"] == "Augusta"
    assert any(w["company"].startswith("Analytical") for w in profile["work_experiences"])
    # Confirmed skills become usable resolver answers.
    assert profile["profile"]["skills_years"]["Python"]["confirmed"] is True
    assert client.get("/api/files").json()[0]["parse_confirmed"] is True


def test_second_resume_not_default_until_set(client):
    headers = register_and_login(client, "f2@example.com")
    first = _upload(client, headers).json()
    second = _upload(client, headers, filename="resume2.txt").json()
    assert second["is_default_resume"] is False

    r = client.post(f"/api/files/{second['id']}/default-resume", headers=headers)
    assert r.status_code == 200
    files = {f["id"]: f for f in client.get("/api/files").json()}
    assert files[second["id"]]["is_default_resume"] is True
    assert files[first["id"]]["is_default_resume"] is False


def test_download_requires_ownership(client):
    headers_a = register_and_login(client, "f3a@example.com")
    file_id = _upload(client, headers_a).json()["id"]
    assert client.get(f"/api/files/{file_id}/download").status_code == 200

    register_and_login(client, "f3b@example.com")  # switches cookie jar to user B
    assert client.get(f"/api/files/{file_id}/download").status_code == 404


def test_upload_rejects_bad_kind_and_empty(client):
    headers = register_and_login(client, "f4@example.com")
    r = _upload(client, headers, kind="screenshot")
    assert r.status_code == 400
    r = client.post(
        "/api/files",
        files={"file": ("empty.txt", io.BytesIO(b""), "text/plain")},
        data={"kind": "resume"},
        headers=headers,
    )
    assert r.status_code == 400
