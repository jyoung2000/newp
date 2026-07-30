"""The single link code: format, round-trip, and what it refuses."""
from __future__ import annotations

import base64
import json

from app.services.link_code import build_link_code, parse_link_code
from tests.conftest import register_and_login


def test_round_trip():
    code = build_link_code("http://192.168.8.119:1456", "123456")
    assert code.startswith("JP1-")
    assert parse_link_code(code) == ("http://192.168.8.119:1456", "123456")


def test_trailing_slash_is_normalised():
    assert parse_link_code(build_link_code("http://host:1456/", "111111"))[0] == "http://host:1456"


def test_payload_shape_is_what_the_extension_parses():
    """The TypeScript parser in extension/src/lib/linkcode.ts decodes this by
    hand, so the shape is a contract between the two and not an implementation
    detail either side may change alone."""
    body = build_link_code("https://jobs.example.com", "654321")[len("JP1-") :]
    padded = body + "=" * (-len(body) % 4)
    data = json.loads(base64.urlsafe_b64decode(padded))
    assert data == {"u": "https://jobs.example.com", "c": "654321"}


def test_garbage_is_rejected_rather_than_guessed():
    for bad in ["", "123456", "JP1-", "JP1-!!!!", "JP1-" + base64.urlsafe_b64encode(b"[]").decode(),
                "http://host:1456", "JP2-abc"]:
        assert parse_link_code(bad) is None, bad


def test_missing_halves_are_rejected():
    for payload in [{"u": "http://h"}, {"c": "1"}, {"u": "", "c": "1"}, {"u": "http://h", "c": ""}]:
        blob = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
        assert parse_link_code("JP1-" + blob) is None


def test_endpoint_returns_a_link_code_for_the_origin_the_browser_used(client):
    """The URL inside has to be the one this browser reached the app on —
    that's the whole point, and it's the one thing the user can't be expected
    to know."""
    headers = register_and_login(client, "pair@example.com")
    r = client.post("/api/devices/pairing-code", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()

    parsed = parse_link_code(body["link_code"])
    assert parsed is not None
    url, code = parsed
    assert code == body["code"]
    assert url == body["app_url"].rstrip("/")
    # TestClient's base_url is http://testserver — not "localhost", which is
    # exactly the substitution that used to be left to the user.
    assert "testserver" in url


def test_the_link_code_actually_pairs(client):
    headers = register_and_login(client, "pair2@example.com")
    body = client.post("/api/devices/pairing-code", headers=headers).json()
    _, code = parse_link_code(body["link_code"])

    r = client.post(
        "/api/ext/pair",
        json={"code": code, "name": "Chrome on Linux", "browser": "chrome",
              "extension_version": "0.1.0"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["user_email"] == "pair2@example.com"
