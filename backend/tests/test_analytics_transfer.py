from __future__ import annotations

import io
import json

from tests.conftest import register_and_login


def _seed_full_profile(client, headers):
    client.put(
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
            "how_heard_default": "Referral",
            "over_18": True,
            "gender": "Woman",
            "skills_years": {"COBOL": {"years": 10, "confirmed": True}},
            "languages": [{"name": "English", "proficiency": "native"}],
        },
        headers=headers,
    )
    client.post(
        "/api/profile/work-experiences",
        json={"title": "Rear Admiral", "company": "US Navy", "bullets": ["Invented the compiler"]},
        headers=headers,
    )
    client.post("/api/profile/educations", json={"school": "Yale", "degree": "PhD"}, headers=headers)
    client.post(
        "/api/profile/recommendations", json={"name": "Howard Aiken"}, headers=headers
    )
    client.post(
        "/api/custom-fields",
        json={"label": "Preferred pronoun", "type": "text", "value": "she/her"},
        headers=headers,
    )
    client.post(
        "/api/saved-answers",
        json={"question_text": "Why this company?", "answer": "Mission alignment"},
        headers=headers,
    )
    client.post(
        "/api/search/targets",
        json={"name": "Compilers", "title_terms": ["compiler engineer"]},
        headers=headers,
    )


def test_dashboard_shape(client):
    headers = register_and_login(client, "an1@example.com")
    client.post(
        "/api/listings/manual", json={"title": "Dev", "company": "Acme"}, headers=headers
    )
    r = client.get("/api/analytics")
    assert r.status_code == 200
    body = r.json()
    assert body["cards"]["total_listings"] == 1
    assert body["cards"]["found_today"] == 1
    assert len(body["funnel"]) == 5
    assert body["funnel"][0]["stage"] == "Found"
    assert len(body["over_time"]) == 31  # default 30 days + today


def test_profile_export_import_round_trip_lossless(client):
    headers = register_and_login(client, "rt@example.com")
    _seed_full_profile(client, headers)

    exported = client.get("/api/transfer/profile.json").json()
    # Sanity: the export carries everything.
    assert exported["profile"]["first_name"] == "Grace"
    assert exported["profile"]["gender"] == "Woman"
    assert len(exported["work_experiences"]) == 1
    assert len(exported["custom_fields"]) == 1
    assert len(exported["saved_answers"]) == 1
    assert len(exported["search_targets"]) == 1

    # Fresh account; import with merge=False to replace.
    headers2 = register_and_login(client, "rt2@example.com")
    blob = io.BytesIO(json.dumps(exported).encode())
    r = client.post(
        "/api/transfer/profile/apply?merge=false",
        files={"file": ("profile.json", blob, "application/json")},
        headers=headers2,
    )
    assert r.status_code == 200, r.text

    reexported = client.get("/api/transfer/profile.json").json()
    # Round-trip: nothing lost. Compare the meaningful sections.
    assert reexported["profile"] == exported["profile"]
    assert reexported["work_experiences"] == exported["work_experiences"]
    assert reexported["educations"] == exported["educations"]
    assert reexported["recommendations"] == exported["recommendations"]
    assert reexported["custom_fields"] == exported["custom_fields"]
    assert reexported["saved_answers"] == exported["saved_answers"]
    assert reexported["search_targets"] == exported["search_targets"]


def test_import_preview_shows_conflicts(client):
    headers = register_and_login(client, "prev@example.com")
    _seed_full_profile(client, headers)
    exported = client.get("/api/transfer/profile.json").json()

    # Import into an account that already has a first name -> conflict.
    headers2 = register_and_login(client, "prev2@example.com")
    client.put("/api/profile", json={"first_name": "Existing"}, headers=headers2)
    blob = io.BytesIO(json.dumps(exported).encode())
    r = client.post(
        "/api/transfer/profile/preview",
        files={"file": ("profile.json", blob, "application/json")},
        headers=headers2,
    )
    assert r.status_code == 200
    preview = r.json()
    assert "first_name" in preview["conflicts"]["profile"]
    assert preview["profile_fields"]["first_name"]["incoming"] == "Grace"
    assert preview["work_experiences"] == 1


def test_merge_import_keeps_existing_values(client):
    headers = register_and_login(client, "merge@example.com")
    _seed_full_profile(client, headers)
    exported = client.get("/api/transfer/profile.json").json()

    headers2 = register_and_login(client, "merge2@example.com")
    client.put("/api/profile", json={"first_name": "Keep"}, headers=headers2)
    blob = io.BytesIO(json.dumps(exported).encode())
    client.post(
        "/api/transfer/profile/apply?merge=true",
        files={"file": ("profile.json", blob, "application/json")},
        headers=headers2,
    )
    profile = client.get("/api/profile").json()["profile"]
    assert profile["first_name"] == "Keep"  # merge preserves the existing value
    assert profile["last_name"] == "Hopper"  # but fills the blanks


def test_listings_csv_round_trip(client):
    headers = register_and_login(client, "csv@example.com")
    client.post(
        "/api/listings/manual",
        json={"title": "Backend Engineer", "company": "Acme", "salary_raw": "$120,000 per year"},
        headers=headers,
    )
    csv_text = client.get("/api/transfer/listings.csv").text
    assert "Backend Engineer" in csv_text and "Acme" in csv_text

    headers2 = register_and_login(client, "csv2@example.com")
    r = client.post(
        "/api/transfer/listings/import",
        files={"file": ("listings.csv", io.BytesIO(csv_text.encode()), "text/csv")},
        headers=headers2,
    )
    assert r.status_code == 200
    assert r.json()["imported"] == 1
    listings = client.get("/api/listings").json()
    assert listings[0]["title"] == "Backend Engineer"


def test_everything_zip(client):
    headers = register_and_login(client, "zip@example.com")
    _seed_full_profile(client, headers)
    client.post(
        "/api/files",
        files={"file": ("resume.txt", io.BytesIO(b"Grace Hopper"), "text/plain")},
        data={"kind": "resume"},
        headers=headers,
    )
    r = client.get("/api/transfer/everything.zip")
    assert r.status_code == 200
    import zipfile

    zf = zipfile.ZipFile(io.BytesIO(r.content))
    names = zf.namelist()
    assert "profile.json" in names
    assert "listings.csv" in names
    assert any(n.startswith("files/resume/") for n in names)
