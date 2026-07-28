"""End-to-end extension-executor flow through the real HTTP API, covering
the Definition-of-Done scenario: claim a job, hit an unknown field, answer it
(as if from a phone) and watch it save to the knowledge base and the job
resume; and a simulated CAPTCHA detection that halts and routes to a human."""
from __future__ import annotations

import io

from tests.conftest import register_and_login


def _bootstrap(client, email):
    headers = register_and_login(client, email)
    client.put(
        "/api/profile",
        json={
            "first_name": "Ada",
            "last_name": "Lovelace",
            "phone": "+1 555 0100",
            "authorized_countries": ["United States"],
            "requires_sponsorship": False,
            "over_18": True,
            "how_heard_default": "Careers page",
        },
        headers=headers,
    )
    client.post(
        "/api/files",
        files={"file": ("r.txt", io.BytesIO(b"Ada Lovelace\nada@x.com"), "text/plain")},
        data={"kind": "resume"},
        headers=headers,
    )
    listing = client.post(
        "/api/listings/manual",
        json={"title": "Backend Engineer", "company": "Acme", "apply_url": "https://acme/apply"},
        headers=headers,
    ).json()
    run = client.post(
        "/api/runs",
        json={"listing_ids": [listing["id"]], "mode": "auto", "executor": "extension"},
        headers=headers,
    ).json()
    code = client.post("/api/devices/pairing-code", headers=headers).json()["code"]
    token = client.post(
        "/api/ext/pair", json={"code": code, "name": "Laptop", "browser": "chrome"}
    ).json()["token"]
    return headers, listing, run, {"authorization": f"Bearer {token}"}


def test_full_extension_flow_with_intervention(client):
    headers, listing, run, dev = _bootstrap(client, "flow1@example.com")

    # 1. Extension claims the next job.
    job = client.post("/api/ext/next-job", headers=dev).json()["job"]
    assert job is not None
    app_id = job["application_id"]
    assert job["listing"]["company"] == "Acme"

    # 2. Extension reports detected fields; server resolves them.
    resolve = client.post(
        f"/api/ext/applications/{app_id}/resolve",
        json={
            "fields": [
                {"label": "First Name", "field_type": "text", "ref": "a", "required": True},
                {"label": "Will you require sponsorship?", "field_type": "radio",
                 "options": ["Yes", "No"], "ref": "b", "required": True},
                {"label": "Describe your ideal team culture", "field_type": "text",
                 "ref": "c", "required": True},
            ]
        },
        headers=dev,
    ).json()
    by_ref = {r["ref"]: r for r in resolve["resolutions"]}
    assert by_ref["a"]["status"] == "resolved" and by_ref["a"]["value"] == "Ada"
    assert by_ref["b"]["status"] == "resolved" and by_ref["b"]["value"] == "No"
    assert by_ref["c"]["status"] == "needs_human"

    # 3. Extension raises an intervention for the unknown field.
    client.post(
        f"/api/ext/applications/{app_id}/interventions",
        json={
            "items": [
                {
                    "kind": "unknown_field",
                    "question": "Describe your ideal team culture",
                    "field_meta": {"label": "Describe your ideal team culture", "field_type": "text"},
                }
            ],
            "reason": "unknown_field",
        },
        headers=dev,
    ).json()["intervention_ids"]
    assert client.get(f"/api/applications/{app_id}", headers=headers).json()["status"] == "needs_human"

    # 4. User answers from the container UI (as if on a phone). Saved to KB.
    open_ivs = client.get("/api/interventions?status=open", headers=headers).json()
    assert len(open_ivs) == 1
    iv = open_ivs[0]
    assert iv["listing_company"] == "Acme"  # enough context to answer remotely
    answered = client.post(
        f"/api/interventions/{iv['id']}/answer",
        json={"answer": "Collaborative, curious, and kind.", "save_to_kb": True},
        headers=headers,
    ).json()
    assert answered["saved_to_kb"] is True

    # The answer is now in the knowledge base and reusable.
    kb = client.get("/api/saved-answers?q=culture", headers=headers).json()
    assert kb and kb[0]["answer"] == "Collaborative, curious, and kind."

    # 5. Extension polls interventions, sees it resolved, resumes the job.
    ext_ivs = client.get(f"/api/ext/applications/{app_id}/interventions", headers=dev).json()
    assert all(i["status"] == "answered" for i in ext_ivs)

    # Re-resolving the same field now returns the saved answer (job resumes).
    reresolve = client.post(
        f"/api/ext/applications/{app_id}/resolve",
        json={"fields": [{"label": "Describe your ideal team culture", "field_type": "text", "ref": "c"}]},
        headers=dev,
    ).json()["resolutions"][0]
    assert reresolve["status"] == "resolved"
    assert reresolve["value"] == "Collaborative, curious, and kind."
    assert reresolve["source"] == "saved_answer"

    # 6. Extension records the submission with snapshot + confirmation shot.
    tiny_png = (
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    )
    r = client.post(
        f"/api/ext/applications/{app_id}/submit-result",
        json={
            "confirmed": True,
            "field_snapshot": {"a": {"value": "Ada"}, "b": {"value": "No"}},
            "screenshot_b64": tiny_png,
        },
        headers=dev,
    )
    assert r.status_code == 200

    detail = client.get(f"/api/applications/{app_id}", headers=headers).json()
    assert detail["status"] == "submitted"
    assert detail["submitted_at"] is not None
    assert detail["field_snapshot"]["a"]["value"] == "Ada"
    assert detail["confirmation_screenshot_url"] is not None
    # The audit trail records the full lifecycle.
    types = [e["type"] for e in detail["events"]]
    assert "status.filling" in types and "status.submitted" in types


def test_simulated_captcha_routes_to_human_not_software(client):
    headers, listing, run, dev = _bootstrap(client, "flow2@example.com")
    job = client.post("/api/ext/next-job", headers=dev).json()["job"]
    app_id = job["application_id"]

    # The content script detected a challenge and halted; it raises a
    # challenge intervention. Software enters nothing further on the page.
    client.post(
        f"/api/ext/applications/{app_id}/interventions",
        json={
            "items": [{"kind": "challenge", "question": "reCAPTCHA appeared",
                       "field_meta": {"detail": "recaptcha iframe", "kind": "challenge"}}],
            "reason": "challenge",
        },
        headers=dev,
    )
    detail = client.get(f"/api/applications/{app_id}", headers=headers).json()
    assert detail["status"] == "needs_human"
    assert detail["needs_human_reason"] == "challenge"

    iv = client.get("/api/interventions?status=open", headers=headers).json()[0]
    assert iv["kind"] == "challenge"

    # A challenge is NOT answerable through the answer endpoint — no software
    # solving path exists. The human solves it in the page, then reports done.
    r = client.post(
        f"/api/interventions/{iv['id']}/answer",
        json={"answer": "solved"},
        headers=headers,
    )
    assert r.status_code == 400  # challenges are not "answered" in software

    r = client.post(f"/api/interventions/{iv['id']}/challenge-done", headers=headers)
    assert r.status_code == 200
    assert r.json()["status"] == "answered"


def test_throughput_ceiling_pauses_extension(client, monkeypatch):
    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "max_applications_per_hour", 0)
    headers, listing, run, dev = _bootstrap(client, "flow3@example.com")
    # With the hourly ceiling at 0, next-job hands out nothing and reports why.
    resp = client.post("/api/ext/next-job", headers=dev).json()
    assert resp["job"] is None
    assert "hour" in (resp["waiting_reason"] or "").lower()
