def test_health_ok(client):
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["database"] == "ok"
    assert payload["version"] == "0.1.0"
    assert payload["uptime_seconds"] >= 0
    assert payload["data_dir"]


def test_health_rejects_bad_token(client):
    response = client.get(
        "/api/v1/health",
        headers={"Authorization": "Bearer wrong-token"},
    )

    assert response.status_code == 401


def test_shutdown_returns_ok(client):
    response = client.post("/api/v1/shutdown")

    assert response.status_code == 200
    assert response.json() == {"ok": True}
