"""One-click capture from the extension: the user is personally looking at a
job page and saves it.

The guarantee this endpoint rests on is narrow and worth stating exactly:
**the server never sends a request to the site the user captured from.** It is
not "no network at all" — a saved listing is summarized and match-scored
through the user's own configured model, exactly like every other listing. The
autouse fixture below intercepts real outbound HTTP and asserts the narrow
claim, and `test_capture_never_touches_the_captured_site` runs it with a live
(mocked-at-the-socket) model call so the interception is not vacuous."""
from __future__ import annotations

import httpx
import pytest
import respx

from tests.conftest import register_and_login

PAGE = {
    "url": "https://careers.example.com/roles/492?utm_source=newsletter",
    "title": "Staff Platform Engineer",
    "company": "Globex",
    "location": "Berlin, DE",
    "description": "Own the deployment platform. Kubernetes, Go, on-call rotation.",
    "salary_raw": "€90,000 - €110,000 per year",
    "apply_url": "https://careers.example.com/roles/492/apply",
    "posted_at_text": "2026-07-01",
    "source_site": "careers.example.com",
}


def _device(client, email: str) -> tuple[dict, dict]:
    """Register a user and pair a device; returns (cookie headers, device headers)."""
    headers = register_and_login(client, email)
    code = client.post("/api/devices/pairing-code", headers=headers).json()["code"]
    token = client.post(
        "/api/ext/pair", json={"code": code, "name": "Laptop", "browser": "chrome"}
    ).json()["token"]
    return headers, {"authorization": f"Bearer {token}"}


CAPTURED_HOSTS = {"careers.example.com", "jobs.example.org"}

# Enough of a Messages response for the SDK to deserialize. The body does not
# have to satisfy the structured-output schema — enrichment failing is handled
# and irrelevant here. What matters is that the request was recorded.
ANTHROPIC_REPLY = {
    "id": "msg_test",
    "type": "message",
    "role": "assistant",
    "model": "claude-opus-5",
    "content": [{"type": "text", "text": "{}"}],
    "stop_reason": "end_turn",
    "stop_sequence": None,
    "usage": {"input_tokens": 10, "output_tokens": 5},
}


@pytest.fixture(autouse=True)
def outbound():
    """Intercepts every outbound HTTP request the server makes in these tests.

    The model provider is answered (so the enrichment path can actually run);
    everything else lands in `other`, which must stay empty. A request to the
    captured job board would show up there and fail the test — that is the one
    guarantee capture depends on."""
    with respx.mock(assert_all_called=False) as mock:
        mock.route(host="api.anthropic.com").mock(
            return_value=httpx.Response(200, json=ANTHROPIC_REPLY)
        )
        other = mock.route().mock(return_value=httpx.Response(599))
        yield mock
    hosts = {call.request.url.host for call in other.calls}
    assert not hosts & CAPTURED_HOSTS, f"JobPilot requested the captured site: {hosts}"
    assert not hosts, f"unexpected outbound request to {hosts}"


def test_capture_saves_the_page_the_user_is_looking_at(client):
    headers, dev = _device(client, "capture-a@example.com")

    saved = client.post("/api/ext/capture", json=PAGE, headers=dev)
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert body["already_saved"] is False
    assert body["title"] == "Staff Platform Engineer"
    assert body["company"] == "Globex"

    # It lands in the user's listings like any other, fully enriched.
    listing = client.get(f"/api/listings/{body['listing_id']}", headers=headers).json()
    assert listing["source"] == "captured"
    assert listing["location"] == "Berlin, DE"
    assert listing["apply_url"] == "https://careers.example.com/roles/492/apply"
    assert listing["salary_min"] == 90000 and listing["salary_max"] == 110000
    assert listing["salary_currency"] == "EUR" and listing["salary_period"] == "year"
    assert listing["posted_at"].startswith("2026-07-01")
    assert listing["extra"]["captured_from"] == "careers.example.com"
    assert "utm_source" not in listing["canonical_url"]  # canonicalized on the way in
    assert listing["summary"] and listing["match_score"] is not None


def test_capturing_the_same_page_twice_does_not_duplicate(client):
    headers, dev = _device(client, "capture-b@example.com")

    first = client.post("/api/ext/capture", json=PAGE, headers=dev).json()
    assert first["already_saved"] is False

    # Same posting, reached through a differently-tracked URL.
    again = {**PAGE, "url": "https://careers.example.com/roles/492/?utm_source=twitter"}
    second = client.post("/api/ext/capture", json=again, headers=dev)
    assert second.status_code == 200, second.text
    assert second.json()["already_saved"] is True
    assert second.json()["listing_id"] == first["listing_id"]

    # And the same role reached through an entirely different site (an
    # aggregator copy) collapses into the row already saved.
    elsewhere = {**PAGE, "url": "https://jobs.example.org/listing/abc123"}
    third = client.post("/api/ext/capture", json=elsewhere, headers=dev)
    assert third.status_code == 200, third.text
    assert third.json()["already_saved"] is True
    assert third.json()["listing_id"] == first["listing_id"]

    assert len(client.get("/api/listings", headers=headers).json()) == 1


def test_capture_stores_only_http_links(client):
    """The page describes itself, so a hostile posting controls these fields.
    The app renders both as links in its own origin — a stored `javascript:`
    URL would run there, so nothing but http(s) is kept."""
    _headers, dev = _device(client, "capture-f@example.com")

    hostile_page = {**PAGE, "url": "javascript:alert(document.cookie)"}
    assert client.post("/api/ext/capture", json=hostile_page, headers=dev).status_code == 422
    assert (
        client.post("/api/ext/capture", json={**PAGE, "url": "not a url"}, headers=dev).status_code
        == 422
    )

    # A bad apply link is not fatal — it falls back to the page URL.
    hostile_apply = {**PAGE, "apply_url": "javascript:fetch('/api/profile')"}
    saved = client.post("/api/ext/capture", json=hostile_apply, headers=dev)
    assert saved.status_code == 200, saved.text
    listing = client.get(
        f"/api/listings/{saved.json()['listing_id']}", headers=_headers
    ).json()
    assert listing["apply_url"] == PAGE["url"]


def test_capture_never_touches_the_captured_site(client, outbound):
    """The claim, exercised with the network path actually live.

    Under the test defaults the LLM layer is offline, so "no request was made"
    proves nothing. Here the user has a real key and offline off: capture does
    reach the network — to their own model provider — and the assertion that
    matters is that not one request goes to the site they captured from."""
    headers, dev = _device(client, "capture-net@example.com")
    saved_settings = client.put(
        "/api/settings/ai",
        json={"api_key": "sk-ant-test-only", "offline": False},
        headers=headers,
    )
    assert saved_settings.status_code == 200, saved_settings.text
    assert saved_settings.json()["effective_offline"] is False

    saved = client.post("/api/ext/capture", json=PAGE, headers=dev)
    assert saved.status_code == 200, saved.text

    hosts = [call.request.url.host for call in outbound.calls]
    # Not vacuous: the enrichment call really was issued and intercepted...
    assert "api.anthropic.com" in hosts
    # ...and the page the user captured was never requested by the server.
    assert not set(hosts) & CAPTURED_HOSTS
    assert set(hosts) == {"api.anthropic.com"}


def test_capture_requires_a_device_token(client):
    register_and_login(client, "capture-c@example.com")
    assert client.post("/api/ext/capture", json=PAGE).status_code == 401
    assert (
        client.post(
            "/api/ext/capture", json=PAGE, headers={"authorization": "Bearer nope"}
        ).status_code
        == 401
    )


def test_captured_listings_are_scoped_to_the_pairing_user(client):
    _a_headers, a_dev = _device(client, "capture-d@example.com")
    listing_id = client.post("/api/ext/capture", json=PAGE, headers=a_dev).json()["listing_id"]

    b_headers, b_dev = _device(client, "capture-e@example.com")
    assert client.get(f"/api/listings/{listing_id}", headers=b_headers).status_code == 404
    assert client.get("/api/listings", headers=b_headers).json() == []

    # B capturing the same page gets their own copy, not A's row.
    b_saved = client.post("/api/ext/capture", json=PAGE, headers=b_dev).json()
    assert b_saved["already_saved"] is False
    assert b_saved["listing_id"] != listing_id
    assert len(client.get("/api/listings", headers=b_headers).json()) == 1
