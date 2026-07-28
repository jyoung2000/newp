def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "version" in body


def test_spa_fallback_without_build(client):
    r = client.get("/some/spa/route")
    assert r.status_code == 200
