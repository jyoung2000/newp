"""One-click autofill: the standalone /api/ext/autofill path.

Distinct from the queue-driven resolve endpoint — no application, no run, no
listing. It answers the question "what goes in this form, from what the user
told JobPilot", and leaves anything it isn't sure of to the human.
"""
from __future__ import annotations

from tests.conftest import register_and_login


def _paired_device(client, email: str) -> dict:
    """A device token, as the extension would hold after pairing."""
    headers = register_and_login(client, email)
    client.put(
        "/api/profile",
        json={
            "first_name": "Ada",
            "last_name": "Lovelace",
            "email": email,
            "phone": "+1 555 0100",
            "city": "London",
            "authorized_countries": ["United States"],
            "requires_sponsorship": False,
            "over_18": True,
            "how_heard_default": "Careers page",
        },
        headers=headers,
    )
    code = client.post("/api/devices/pairing-code", headers=headers).json()["code"]
    token = client.post(
        "/api/ext/pair",
        json={"code": code, "name": "Chrome", "browser": "chrome", "extension_version": "0.1.0"},
    ).json()["token"]
    return {"authorization": f"Bearer {token}"}


def _field(label: str, **kw) -> dict:
    return {
        "ref": kw.pop("ref", label.lower().replace(" ", "-")),
        "label": label,
        "field_type": kw.pop("field_type", "text"),
        "options": kw.pop("options", []),
        "required": kw.pop("required", False),
        "name": kw.pop("name", None),
        "surrounding_text": kw.pop("surrounding_text", ""),
    }


def test_autofill_answers_from_the_profile(client):
    device = _paired_device(client, "fill@example.com")
    r = client.post(
        "/api/ext/autofill",
        json={
            "url": "https://boards.example.com/apply",
            "title": "Apply",
            "fields": [
                _field("First name"),
                _field("Last name"),
                _field("Phone"),
            ],
        },
        headers=device,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    by_ref = {x["ref"]: x for x in body["resolutions"]}
    assert by_ref["first-name"]["status"] == "resolved"
    assert by_ref["first-name"]["formatted"] == "Ada"
    assert by_ref["last-name"]["formatted"] == "Lovelace"
    assert body["filled"] >= 2
    # Counts are reported so the extension can say what happened.
    assert body["filled"] + body["needs_human"] == len(body["resolutions"])


def test_no_application_or_run_is_required(client):
    """The whole point: the user is on a form JobPilot never queued."""
    device = _paired_device(client, "adhoc@example.com")
    r = client.post(
        "/api/ext/autofill",
        json={"url": "https://random.example/careers", "title": "", "fields": [_field("Email")]},
        headers=device,
    )
    assert r.status_code == 200
    assert r.json()["resolutions"][0]["status"] == "resolved"


def test_a_question_it_cannot_answer_goes_to_the_human(client):
    device = _paired_device(client, "unknown@example.com")
    r = client.post(
        "/api/ext/autofill",
        json={
            "url": "https://x/apply",
            "title": "",
            "fields": [
                _field(
                    "Describe a time you disagreed with your manager",
                    field_type="textarea",
                    required=True,
                )
            ],
        },
        headers=device,
    )
    assert r.status_code == 200, r.text
    res = r.json()["resolutions"][0]
    # Never a guess: either it has an answer, or it says a human is needed.
    assert res["status"] != "resolved" or res["value"]
    if res["status"] != "resolved":
        assert r.json()["needs_human"] == 1


def test_autofill_requires_a_device_token(client):
    register_and_login(client, "noauth@example.com")
    r = client.post(
        "/api/ext/autofill", json={"url": "", "title": "", "fields": [_field("First name")]}
    )
    assert r.status_code == 401


def test_one_users_answers_never_reach_another_device(client):
    """Device tokens are per-user; autofill must resolve from the token's owner
    and nobody else."""
    a = _paired_device(client, "alice@example.com")
    b = _paired_device(client, "bob@example.com")

    ra = client.post(
        "/api/ext/autofill",
        json={"url": "", "title": "", "fields": [_field("Email")]},
        headers=a,
    ).json()
    rb = client.post(
        "/api/ext/autofill",
        json={"url": "", "title": "", "fields": [_field("Email")]},
        headers=b,
    ).json()
    assert ra["resolutions"][0]["formatted"] == "alice@example.com"
    assert rb["resolutions"][0]["formatted"] == "bob@example.com"


def test_ocr_label_is_unavailable_offline_rather_than_guessing(client):
    """Tests run with LLM_DRY_RUN=1, i.e. exactly the offline case: nothing is
    sent anywhere, and the caller is told so instead of being handed a guess."""
    device = _paired_device(client, "ocr@example.com")
    r = client.post(
        "/api/ext/ocr-label",
        # 1x1 transparent PNG.
        json={
            "image_b64": (
                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
            ),
            "nearby_text": "",
        },
        headers=device,
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"text": "", "available": False}


def test_ocr_label_rejects_an_oversized_image(client):
    device = _paired_device(client, "big@example.com")
    r = client.post(
        "/api/ext/ocr-label",
        json={"image_b64": "A" * 400_001, "nearby_text": ""},
        headers=device,
    )
    assert r.status_code == 422
