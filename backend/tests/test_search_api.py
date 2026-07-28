from __future__ import annotations

import json
import time
from pathlib import Path

import respx
from httpx import Response

from tests.conftest import register_and_login

FIXTURES = Path(__file__).parent / "fixtures"


def test_search_run_via_api_with_progress(client, monkeypatch):
    # Kill pacing for the test run so the background thread finishes fast.
    from app.sources import http as http_mod

    http_mod.reset_http()
    monkeypatch.setattr(http_mod.PoliteHttpClient, "min_interval", 0.0, raising=False)

    headers = register_and_login(client, "search1@example.com")
    with respx.mock(assert_all_called=False) as router:
        router.get("https://www.arbeitnow.com/api/job-board-api").mock(
            return_value=Response(200, json=json.loads((FIXTURES / "arbeitnow.json").read_text()))
        )
        r = client.post(
            "/api/search/run",
            json={"terms": ["python"], "sources": ["arbeitnow"]},
            headers=headers,
        )
        assert r.status_code == 200, r.text
        run_id = r.json()["run_id"]

        for _ in range(100):
            status = client.get(f"/api/search/runs/{run_id}").json()
            if status["status"] in ("completed", "failed"):
                break
            time.sleep(0.05)
        assert status["status"] == "completed", status
        assert status["per_source"]["arbeitnow"]["status"] == "done"
        assert status["new"] == 1

    listings = client.get("/api/listings").json()
    assert len(listings) == 1
    row = listings[0]
    assert row["title"] == "Python Backend Developer"
    assert row["summary"]  # enrichment ran (dry-run deterministic)
    assert row["match_score"] is not None

    # Repeat run: cache + dedupe -> no new listings.
    with respx.mock(assert_all_called=False) as router:
        router.get("https://www.arbeitnow.com/api/job-board-api").mock(
            return_value=Response(200, json=json.loads((FIXTURES / "arbeitnow.json").read_text()))
        )
        run_id = client.post(
            "/api/search/run",
            json={"terms": ["python"], "sources": ["arbeitnow"]},
            headers=headers,
        ).json()["run_id"]
        for _ in range(100):
            status = client.get(f"/api/search/runs/{run_id}").json()
            if status["status"] in ("completed", "failed"):
                break
            time.sleep(0.05)
        assert status["status"] == "completed"
        assert status["new"] == 0
    http_mod.reset_http()


def test_sources_endpoint_reports_statuses(client):
    register_and_login(client, "search2@example.com")
    infos = {s["name"]: s for s in client.get("/api/search/sources").json()}
    assert infos["linkedin"]["forbidden"] is True
    assert infos["linkedin"]["status"] == "forbidden"
    assert "prohibit" in infos["linkedin"]["permission_basis"].lower()
    assert infos["adzuna"]["requires_key"] is True
    assert infos["adzuna"]["configured"] is False
    assert infos["greenhouse"]["configured"] is True
    assert infos["websearch"]["status"] == "disabled"  # no key in tests


def test_search_targets_crud_and_run(client, monkeypatch):
    from app.sources import http as http_mod

    http_mod.reset_http()
    monkeypatch.setattr(http_mod.PoliteHttpClient, "min_interval", 0.0, raising=False)
    headers = register_and_login(client, "search3@example.com")
    r = client.post(
        "/api/search/targets",
        json={
            "name": "Python remote",
            "title_terms": ["python"],
            "remote": True,
            "sources": ["arbeitnow"],
            "schedule_minutes": 60,
        },
        headers=headers,
    )
    assert r.status_code == 201
    target_id = r.json()["id"]
    assert client.get("/api/search/targets").json()[0]["name"] == "Python remote"

    with respx.mock(assert_all_called=False) as router:
        router.get("https://www.arbeitnow.com/api/job-board-api").mock(
            return_value=Response(200, json={"data": []})
        )
        r = client.post(f"/api/search/targets/{target_id}/run", headers=headers)
        assert r.status_code == 200
        run_id = r.json()["run_id"]
        for _ in range(100):
            status = client.get(f"/api/search/runs/{run_id}").json()
            if status["status"] in ("completed", "failed"):
                break
            time.sleep(0.05)
        assert status["status"] == "completed"

    assert client.get("/api/search/targets").json()[0]["last_run_at"] is not None
    assert client.delete(f"/api/search/targets/{target_id}", headers=headers).status_code == 200
    http_mod.reset_http()


def test_manual_add_without_url(client):
    headers = register_and_login(client, "manual1@example.com")
    r = client.post(
        "/api/listings/manual",
        json={
            "title": "Librarian",
            "company": "City Library",
            "description": "Catalog books",
            "salary_raw": "$52,000 per year",
        },
        headers=headers,
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["source"] == "manual"
    assert body["salary_min"] == 52000
    assert body["summary"]  # enriched

    # One application per posting also implies one saved copy per posting.
    r = client.get("/api/listings")
    assert len(r.json()) == 1


def test_manual_add_with_ats_url_harvests_org(client, monkeypatch):
    from app.sources import http as http_mod

    http_mod.reset_http()
    monkeypatch.setattr(http_mod.PoliteHttpClient, "min_interval", 0.0, raising=False)
    headers = register_and_login(client, "manual2@example.com")
    html = (FIXTURES / "jsonld_page.html").read_text()
    with respx.mock(assert_all_called=False) as router:
        router.get("https://boards.greenhouse.io/robots.txt").mock(return_value=Response(404))
        router.get("https://boards.greenhouse.io/wonka/jobs/77").mock(
            return_value=Response(200, text=html, headers={"content-type": "text/html"})
        )
        r = client.post(
            "/api/listings/manual",
            json={"url": "https://boards.greenhouse.io/wonka/jobs/77"},
            headers=headers,
        )
    assert r.status_code == 201, r.text
    assert r.json()["title"] == "Confectionery Automation Engineer"
    assert r.json()["salary_currency"] == "CHF"
    http_mod.reset_http()
