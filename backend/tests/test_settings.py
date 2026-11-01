def test_settings_defaults(client):
    response = client.get("/api/v1/settings")

    assert response.status_code == 200
    payload = response.json()
    assert payload["poll_interval_minutes"] == 30
    assert payload["checkout_interval_hours"] == 6
    assert payload["notification_channel"] == "serverchan"
    assert payload["close_to_tray"] is True
    assert payload["onboarding_completed"] is False


def test_settings_patch_persists(client):
    response = client.patch(
        "/api/v1/settings",
        json={
            "poll_interval_minutes": 45,
            "notification_channel": "pushplus",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["poll_interval_minutes"] == 45
    assert payload["notification_channel"] == "pushplus"

    again = client.get("/api/v1/settings").json()
    assert again["poll_interval_minutes"] == 45
    assert again["notification_channel"] == "pushplus"


def test_settings_rejects_invalid_interval(client):
    response = client.patch("/api/v1/settings", json={"poll_interval_minutes": 5})

    assert response.status_code == 422


def test_onboarding_completion_persists(client):
    response = client.patch(
        "/api/v1/settings", json={"onboarding_completed": True}
    )

    assert response.status_code == 200
    assert response.json()["onboarding_completed"] is True
    assert client.get("/api/v1/settings").json()["onboarding_completed"] is True
