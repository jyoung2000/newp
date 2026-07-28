from __future__ import annotations

import pyotp

from tests.conftest import register_and_login


def test_register_login_me_logout(client):
    headers = register_and_login(client, "a@example.com")
    r = client.get("/api/auth/me")
    assert r.status_code == 200
    assert r.json()["email"] == "a@example.com"

    r = client.post("/api/auth/logout", headers=headers)
    assert r.status_code == 200
    assert client.get("/api/auth/me").status_code == 401


def test_duplicate_email_rejected(client):
    register_and_login(client, "dup@example.com")
    r = client.post("/api/auth/register", json={"email": "dup@example.com", "password": "x" * 12})
    assert r.status_code == 409


def test_wrong_password_rejected(client):
    register_and_login(client, "b@example.com")
    r = client.post("/api/auth/login", json={"email": "b@example.com", "password": "wrong-pass-1"})
    assert r.status_code == 401


def test_short_password_rejected(client):
    r = client.post("/api/auth/register", json={"email": "c@example.com", "password": "short"})
    assert r.status_code == 422


def test_login_rate_limited(client):
    client.post("/api/auth/register", json={"email": "rl@example.com", "password": "x" * 12})
    codes = []
    for _ in range(12):
        r = client.post("/api/auth/login", json={"email": "rl@example.com", "password": "bad-pass-123"})
        codes.append(r.status_code)
    assert 429 in codes


def test_csrf_required_for_mutations(client):
    register_and_login(client, "csrf@example.com")
    # No CSRF header on a cookie-authed mutation -> 403.
    r = client.post("/api/auth/logout")
    assert r.status_code == 403
    # GETs never need it.
    assert client.get("/api/auth/me").status_code == 200


def test_totp_flow(client):
    headers = register_and_login(client, "totp@example.com")
    r = client.post("/api/auth/totp/setup", headers=headers)
    assert r.status_code == 200
    secret = r.json()["secret"]
    assert "svg" in r.json()["qr_svg"]

    code = pyotp.TOTP(secret).now()
    assert client.post("/api/auth/totp/enable", json={"code": code}, headers=headers).status_code == 200

    # Fresh login now requires the TOTP step; the half-open session is unusable.
    r = client.post("/api/auth/login", json={"email": "totp@example.com", "password": "correct horse 9!"})
    assert r.status_code == 200 and r.json()["requires_totp"] is True
    assert client.get("/api/auth/me").status_code == 401

    r = client.post("/api/auth/totp", json={"code": "000000"})
    assert r.status_code == 401
    r = client.post("/api/auth/totp", json={"code": pyotp.TOTP(secret).now()})
    assert r.status_code == 200 and r.json()["csrf_token"]
    assert client.get("/api/auth/me").status_code == 200


def test_change_password_revokes_other_sessions(client):
    register_and_login(client, "pw@example.com")
    # Second login: the cookie jar now holds this newer session.
    new_csrf = client.post(
        "/api/auth/login", json={"email": "pw@example.com", "password": "correct horse 9!"}
    ).json()["csrf_token"]
    assert new_csrf
    r = client.post(
        "/api/auth/change-password",
        json={"current_password": "correct horse 9!", "new_password": "even better horse 10!"},
        headers={"x-csrf-token": new_csrf},
    )
    assert r.status_code == 200
    sessions = client.get("/api/auth/sessions").json()
    assert len(sessions) == 1
    r = client.post("/api/auth/login", json={"email": "pw@example.com", "password": "even better horse 10!"})
    assert r.status_code == 200


def test_settings_roundtrip(client):
    headers = register_and_login(client, "settings@example.com")
    r = client.get("/api/auth/settings")
    assert r.status_code == 200
    body = r.json()
    assert body["humanize_default"] is True
    body["run_mode_default"] = "auto"
    body["notifications"]["webhook_enabled"] = True
    body["notifications"]["webhook_url"] = "https://ntfy.sh/my-topic"
    r = client.put("/api/auth/settings", json=body, headers=headers)
    assert r.status_code == 200
    assert client.get("/api/auth/settings").json()["run_mode_default"] == "auto"


def test_delete_account(client):
    headers = register_and_login(client, "gone@example.com")
    r = client.delete("/api/auth/account", headers=headers)
    assert r.status_code == 200
    r = client.post("/api/auth/login", json={"email": "gone@example.com", "password": "correct horse 9!"})
    assert r.status_code == 401
