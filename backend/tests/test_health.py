from app import __version__


def test_health_ok(client):
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["database"] == "ok"
    assert payload["version"] == __version__
    assert payload["uptime_seconds"] >= 0
    assert payload["data_dir"]


def test_health_rejects_bad_token(client):
    response = client.get(
        "/api/v1/health",
        headers={"Authorization": "Bearer wrong-token"},
    )

    assert response.status_code == 401


def test_model_search_route_removed_but_link_resolve_route_remains(client):
    assert not any(
        getattr(route, "path", None) == "/api/v1/listings/search-model"
        for route in client.app.routes
    )
    assert client.post("/api/v1/listings/search-model", json={}).status_code == 405
    assert client.post(
        "/api/v1/listings/resolve", json={"url": "https://example.com/item"},
    ).status_code == 422


def test_shutdown_returns_ok(client):
    response = client.post("/api/v1/shutdown")

    assert response.status_code == 200
    assert response.json() == {"ok": True}
