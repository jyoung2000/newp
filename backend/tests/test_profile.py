from __future__ import annotations

from tests.conftest import register_and_login


def test_profile_roundtrip_and_completeness(client):
    headers = register_and_login(client, "p1@example.com")
    r = client.get("/api/profile")
    assert r.status_code == 200
    body = r.json()
    assert body["profile"]["email"] == "p1@example.com"
    assert body["completeness"] < 100
    assert "Default resume" in body["completeness_missing"]

    r = client.put(
        "/api/profile",
        json={
            "first_name": "Grace",
            "last_name": "Hopper",
            "phone": "+1 555 0101",
            "city": "Arlington",
            "country": "United States",
            "authorized_countries": ["United States"],
            "requires_sponsorship": False,
            "salary_expectation_amount": 150000,
            "salary_expectation_currency": "USD",
            "salary_expectation_period": "year",
            "total_years_experience": 12,
            "how_heard_default": "Job board",
            "over_18": True,
            "skills_years": {"COBOL": {"years": 10, "confirmed": True}},
        },
        headers=headers,
    )
    assert r.status_code == 200, r.text
    body = client.get("/api/profile").json()
    assert body["profile"]["first_name"] == "Grace"
    assert body["profile"]["skills_years"]["COBOL"]["confirmed"] is True
    # EEO defaults remain decline until the user chooses otherwise.
    assert body["profile"]["gender"] == "decline"


def test_work_experience_crud_and_reorder(client):
    headers = register_and_login(client, "p2@example.com")
    ids = []
    for title in ("Engineer", "Senior Engineer"):
        r = client.post(
            "/api/profile/work-experiences",
            json={"title": title, "company": "Acme", "bullets": ["Did things"]},
            headers=headers,
        )
        assert r.status_code == 201
        ids.append(r.json()["id"])

    r = client.post(
        "/api/profile/work-experiences/reorder", json={"ids": ids[::-1]}, headers=headers
    )
    assert r.status_code == 200
    listed = client.get("/api/profile").json()["work_experiences"]
    assert listed[0]["title"] == "Senior Engineer"

    r = client.put(
        f"/api/profile/work-experiences/{ids[0]}",
        json={"title": "Staff Engineer", "company": "Acme"},
        headers=headers,
    )
    assert r.status_code == 200 and r.json()["title"] == "Staff Engineer"

    assert (
        client.delete(f"/api/profile/work-experiences/{ids[1]}", headers=headers).status_code
        == 200
    )
    assert len(client.get("/api/profile").json()["work_experiences"]) == 1


def test_custom_fields_validation(client):
    headers = register_and_login(client, "p3@example.com")
    r = client.post(
        "/api/custom-fields",
        json={"label": "Willing to travel", "type": "select", "options": ["Yes", "No"], "value": "Yes"},
        headers=headers,
    )
    assert r.status_code == 201
    assert r.json()["key"] == "willing to travel"

    r = client.post(
        "/api/custom-fields",
        json={"label": "Willing to travel", "type": "text", "value": "x"},
        headers=headers,
    )
    assert r.status_code == 409  # duplicate label

    r = client.post(
        "/api/custom-fields",
        json={"label": "Bad select", "type": "select", "options": ["A"], "value": "B"},
        headers=headers,
    )
    assert r.status_code == 422


def test_saved_answers_crud_and_search(client):
    headers = register_and_login(client, "p4@example.com")
    r = client.post(
        "/api/saved-answers",
        json={"question_text": "What is your notice period?", "answer": "Two weeks"},
        headers=headers,
    )
    assert r.status_code == 201
    answer_id = r.json()["id"]
    assert r.json()["question_key"] == "what is your notice period"

    assert client.get("/api/saved-answers?q=notice").json()[0]["id"] == answer_id
    assert client.get("/api/saved-answers?q=zzz").json() == []

    r = client.put(
        f"/api/saved-answers/{answer_id}",
        json={
            "question_text": "What is your notice period?",
            "answer": "Three weeks",
            "question_key": "notice period",
        },
        headers=headers,
    )
    assert r.status_code == 200 and r.json()["question_key"] == "notice period"

    assert client.delete(f"/api/saved-answers/{answer_id}", headers=headers).status_code == 200
