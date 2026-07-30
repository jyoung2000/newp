"""The head admin: who gets the role, and what it does and does not permit."""
from __future__ import annotations

from tests.conftest import register_and_login

PASSWORD = "correct horse 9!"


def _login(client, email: str, password: str = PASSWORD) -> dict:
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"x-csrf-token": r.json()["csrf_token"]}


def test_first_account_is_admin_and_the_second_is_not(client):
    register_and_login(client, "first@example.com")
    assert client.get("/api/auth/me").json()["is_admin"] is True

    # A second registration must not inherit the role.
    register_and_login(client, "second@example.com")
    assert client.get("/api/auth/me").json()["is_admin"] is False


def test_seeded_demo_account_does_not_take_the_role(client, engine):
    """The demo account is created unattended with a published password, so it
    must not become the head admin — and it must not stop the first real
    registration from becoming one."""
    from sqlalchemy.orm import Session

    from app.models import User
    from app.security import hash_password

    with Session(engine) as db:
        db.add(
            User(
                email="demo@jobpilot.local",
                password_hash=hash_password(PASSWORD),
                settings={},
                is_admin=False,
            )
        )
        db.commit()

    register_and_login(client, "human@example.com")
    me = client.get("/api/auth/me").json()
    assert me["is_admin"] is True, "the first real account should still get the role"


def test_non_admin_is_refused_user_management(client):
    register_and_login(client, "owner@example.com")
    client.post("/api/auth/logout", headers=_login(client, "owner@example.com"))

    headers = register_and_login(client, "regular@example.com")
    assert client.get("/api/users").status_code == 403
    assert (
        client.post(
            "/api/users",
            json={"email": "x@example.com", "password": PASSWORD},
            headers=headers,
        ).status_code
        == 403
    )
    assert client.delete("/api/users/1", headers=headers).status_code == 403


def test_admin_lists_creates_promotes_and_resets(client):
    headers = register_and_login(client, "admin@example.com")

    r = client.get("/api/users")
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 1
    assert rows[0]["is_self"] is True and rows[0]["is_admin"] is True

    # Create an account on someone's behalf.
    r = client.post(
        "/api/users",
        json={"email": "hire@example.com", "password": PASSWORD},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    new_id = r.json()["id"]
    assert r.json()["is_admin"] is False

    # It can actually be used, and it has a profile like a self-registration.
    assert client.post(
        "/api/auth/login", json={"email": "hire@example.com", "password": PASSWORD}
    ).status_code == 200
    headers = _login(client, "admin@example.com")

    # Promote, then demote.
    r = client.patch(f"/api/users/{new_id}", json={"is_admin": True}, headers=headers)
    assert r.status_code == 200 and r.json()["is_admin"] is True
    r = client.patch(f"/api/users/{new_id}", json={"is_admin": False}, headers=headers)
    assert r.status_code == 200 and r.json()["is_admin"] is False

    # Reset the password; the old one stops working and the new one starts.
    r = client.post(
        f"/api/users/{new_id}/password",
        json={"new_password": "a whole new pass 7"},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    headers = _login(client, "admin@example.com")
    assert client.post(
        "/api/auth/login", json={"email": "hire@example.com", "password": PASSWORD}
    ).status_code == 401
    assert client.post(
        "/api/auth/login",
        json={"email": "hire@example.com", "password": "a whole new pass 7"},
    ).status_code == 200


def test_admin_password_reset_revokes_that_users_sessions(client):
    headers = register_and_login(client, "admin2@example.com")
    r = client.post(
        "/api/users", json={"email": "victim@example.com", "password": PASSWORD}, headers=headers
    )
    target_id = r.json()["id"]

    # The target signs in, holding a live session.
    victim = _login(client, "victim@example.com")
    assert client.get("/api/auth/me").json()["email"] == "victim@example.com"

    headers = _login(client, "admin2@example.com")
    client.post(
        f"/api/users/{target_id}/password",
        json={"new_password": "rotated pass 12345"},
        headers=headers,
    )
    # The victim's cookie is dead even though the client still holds it.
    client.cookies.clear()
    assert client.get("/api/auth/me", headers=victim).status_code == 401


def test_last_admin_cannot_be_demoted_or_deleted(client):
    headers = register_and_login(client, "solo@example.com")
    me = client.get("/api/auth/me").json()

    r = client.patch(f"/api/users/{me['id']}", json={"is_admin": False}, headers=headers)
    assert r.status_code == 409
    assert "only administrator" in r.json()["detail"]

    # Still an admin afterwards.
    assert client.get("/api/auth/me").json()["is_admin"] is True

    # Promoting a second admin unlocks both.
    r = client.post(
        "/api/users", json={"email": "second@example.com", "password": PASSWORD, "is_admin": True},
        headers=headers,
    )
    assert r.status_code == 201
    r = client.patch(f"/api/users/{me['id']}", json={"is_admin": False}, headers=headers)
    assert r.status_code == 200 and r.json()["is_admin"] is False


def test_sole_account_can_still_delete_itself(client):
    """A one-person install: the only account is also the admin, and deleting
    it is just leaving. Refusing would strand nobody and lock the owner out of
    removing their own data permanently."""
    headers = register_and_login(client, "only@example.com")
    r = client.delete("/api/auth/account", headers=headers)
    assert r.status_code == 200, r.text

    # And the install is back to its pre-registration state: the next account
    # to register takes the role.
    register_and_login(client, "next@example.com")
    assert client.get("/api/auth/me").json()["is_admin"] is True


def test_last_admin_cannot_abandon_other_accounts(client):
    """Same deletion, but other people now depend on this install having an
    administrator."""
    headers = register_and_login(client, "chief@example.com")
    client.post(
        "/api/users", json={"email": "staff@example.com", "password": PASSWORD}, headers=headers
    )
    r = client.delete("/api/auth/account", headers=headers)
    assert r.status_code == 409
    assert "only administrator" in r.json()["detail"]


def test_admin_cannot_delete_own_account_from_user_management(client):
    headers = register_and_login(client, "self@example.com")
    client.post(
        "/api/users", json={"email": "other@example.com", "password": PASSWORD, "is_admin": True},
        headers=headers,
    )
    me = client.get("/api/auth/me").json()
    r = client.delete(f"/api/users/{me['id']}", headers=headers)
    assert r.status_code == 409
    assert "Danger zone" in r.json()["detail"]


def test_admin_deletes_another_account(client):
    headers = register_and_login(client, "boss@example.com")
    r = client.post(
        "/api/users", json={"email": "gone@example.com", "password": PASSWORD}, headers=headers
    )
    target_id = r.json()["id"]

    r = client.delete(f"/api/users/{target_id}", headers=headers)
    assert r.status_code == 200, r.text
    assert client.post(
        "/api/auth/login", json={"email": "gone@example.com", "password": PASSWORD}
    ).status_code == 401
    assert [u["id"] for u in client.get("/api/users").json()] == [1]


def test_admin_role_grants_no_access_to_another_users_data(client):
    """Managing accounts is not reading them. The isolation guarantee has to
    survive the new role, or 'admin' quietly becomes 'can read your job hunt'."""
    admin = register_and_login(client, "admin3@example.com")
    r = client.post(
        "/api/users", json={"email": "private@example.com", "password": PASSWORD}, headers=admin
    )
    other_id = r.json()["id"]

    # The other user stores something of their own.
    other = _login(client, "private@example.com")
    client.post(
        "/api/saved-answers",
        json={"question": "Why us?", "answer": "secret answer"},
        headers=other,
    )

    # The admin sees none of it through their own scoped endpoints.
    admin = _login(client, "admin3@example.com")
    rows = client.get("/api/saved-answers").json()
    assert all("secret answer" != row.get("answer") for row in rows)

    # And there is no admin route that reads another account's data — the
    # management surface exposes accounts only.
    listed = client.get("/api/users").json()
    keys = set(listed[0].keys())
    assert keys == {
        "id",
        "email",
        "is_admin",
        "totp_enabled",
        "created_at",
        "last_seen_at",
        "active_sessions",
        "is_self",
    }
    assert other_id in [u["id"] for u in listed]
