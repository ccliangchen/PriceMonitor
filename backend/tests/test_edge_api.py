from app.api.routes_edge_bridge import PageObservation
from app.services.edge_bridge import edge_bridge


def test_product_observation_keeps_price_and_seller():
    observation = PageObservation.model_validate({
        "url": "https://item.jd.com/123456789.html",
        "price_texts": ["3999"],
        "shop_texts": ["iQOO京东自营旗舰店"],
    })
    payload = observation.model_dump(exclude={"browser"})
    assert payload["price_texts"] == ["3999"]
    assert payload["shop_texts"] == ["iQOO京东自营旗舰店"]


def test_jd_frequency_status_is_a_warning_only(client):
    previous = edge_bridge.jd_pacer.frequency_warning
    try:
        edge_bridge.jd_pacer.frequency_warning = True
        status = client.get("/api/v1/edge/status").json()
        assert status["jd_frequency_warning"] is True
    finally:
        edge_bridge.jd_pacer.frequency_warning = previous


def test_single_extension_claim_reports_both_platform_capabilities(client):
    edge_bridge.last_seen.clear()
    try:
        old = client.post("/api/v1/edge/claim", json={})
        assert old.status_code == 200
        assert old.json() == {"job": None}
        assert client.get("/api/v1/edge/status").json()["platforms"] == ["jd"]

        new = client.post(
            "/api/v1/edge/claim", json={"capabilities": ["jd", "taobao"]}
        )
        assert new.status_code == 200
        assert new.json() == {"job": None}
        assert client.get("/api/v1/edge/status").json()["platforms"] == [
            "jd",
            "taobao",
        ]
    finally:
        edge_bridge.last_seen.clear()


def test_switch_browser_changes_which_extension_is_connected(client):
    edge_bridge.last_seen.clear()
    try:
        assert client.patch(
            "/api/v1/settings", json={"capture_browser": "chrome"}
        ).status_code == 200
        client.post(
            "/api/v1/edge/claim",
            json={"browser": "edge", "capabilities": ["jd", "taobao"]},
        )
        status = client.get("/api/v1/edge/status").json()
        assert status["selected_browser"] == "chrome"
        assert status["connected"] is False
        assert status["connected_browsers"] == ["edge"]

        client.post(
            "/api/v1/edge/claim",
            json={"browser": "chrome", "capabilities": ["jd", "taobao"]},
        )
        status = client.get("/api/v1/edge/status").json()
        assert status["connected"] is True
        assert status["platforms"] == ["jd", "taobao"]

        assert client.patch(
            "/api/v1/settings", json={"capture_browser": "firefox"}
        ).status_code == 200
        assert client.get("/api/v1/edge/status").json()["connected"] is False
    finally:
        edge_bridge.last_seen.clear()
