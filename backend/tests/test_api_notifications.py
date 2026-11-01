def test_save_serverchan_key_uses_put_route(client, monkeypatch):
    from app.api import routes_notifications

    saved: list[str] = []
    monkeypatch.setattr(
        routes_notifications, "set_serverchan_key", lambda value: saved.append(value)
    )
    monkeypatch.setattr(
        routes_notifications, "is_notification_configured", lambda: True
    )

    response = client.put(
        "/api/v1/notifications/serverchan",
        json={"serverchan_sendkey": "SCT-test-key"},
    )

    assert response.status_code == 200
    assert response.json()["serverchan_configured"] is True
    assert saved == ["SCT-test-key"]
