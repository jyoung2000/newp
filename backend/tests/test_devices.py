from __future__ import annotations

from tests.conftest import register_and_login


def test_pairing_flow(client):
    headers = register_and_login(client, "d1@example.com")
    r = client.post("/api/devices/pairing-code", headers=headers)
    assert r.status_code == 200
    code = r.json()["code"]
    assert len(code) == 6 and code.isdigit()
    assert "svg" in r.json()["qr_svg"]

    # The extension exchanges the code without any cookie auth.
    r = client.post(
        "/api/ext/pair",
        json={"code": code, "name": "Work laptop", "browser": "chrome"},
    )
    assert r.status_code == 200, r.text
    token = r.json()["token"]
    assert r.json()["user_email"] == "d1@example.com"

    # Codes are one-time.
    r = client.post("/api/ext/pair", json={"code": code, "name": "Again", "browser": "chrome"})
    assert r.status_code == 401

    # The token authenticates /ext endpoints.
    r = client.get("/api/ext/ping", headers={"authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["device_name"] == "Work laptop"

    # Devices are listed and revocable; revoked tokens stop working.
    devices = client.get("/api/devices").json()
    assert len(devices) == 1
    device_id = devices[0]["id"]
    assert client.delete(f"/api/devices/{device_id}", headers=headers).status_code == 200
    r = client.get("/api/ext/ping", headers={"authorization": f"Bearer {token}"})
    assert r.status_code == 401


def test_bad_pairing_code_rejected(client):
    register_and_login(client, "d2@example.com")
    r = client.post("/api/ext/pair", json={"code": "000000", "name": "X", "browser": "chrome"})
    assert r.status_code == 401


def test_new_pairing_code_invalidates_old(client):
    headers = register_and_login(client, "d3@example.com")
    first = client.post("/api/devices/pairing-code", headers=headers).json()["code"]
    second = client.post("/api/devices/pairing-code", headers=headers).json()["code"]
    r = client.post("/api/ext/pair", json={"code": first, "name": "X", "browser": "chrome"})
    assert r.status_code == 401
    r = client.post("/api/ext/pair", json={"code": second, "name": "X", "browser": "chrome"})
    assert r.status_code == 200
