def product_payload() -> dict:
    return {
        "name": "iQOO Neo11 至尊版 12GB+512GB",
        "brand": "iQOO",
        "model": "Neo11",
        "variant": "至尊版",
        "ram_gb": 12,
        "storage_gb": 512,
        "color": None,
        "notes": None,
        "listing": {
            "platform": "jd",
            "url": "https://item.jd.com/100.html",
            "title": "iQOO Neo11 至尊版 12GB+512GB",
            "shop_name": "iQOO京东自营旗舰店",
            "shop_type": "jd_official_self",
            "platform_item_id": "100",
            "platform_sku_id": None,
            "shop_evidence": {"self_operated": "true", "shop_brand": "iQOO"},
            "detected_specs": {"ram_gb": "12", "storage_gb": "512"},
        },
    }


def test_create_list_detail_delete_product(client):
    response = client.post("/api/v1/products", json=product_payload())

    assert response.status_code == 200
    summary = response.json()
    assert summary["name"] == "iQOO Neo11 至尊版 12GB+512GB"
    assert summary["current_price_cents"] is None
    assert summary["history_low_cents"] is None
    assert summary["status"] == "active"
    product_id = summary["id"]

    detail = client.get(f"/api/v1/products/{product_id}").json()
    assert len(detail["listings"]) == 1
    assert detail["listings"][0]["shop_verified"] is True
    assert detail["listings"][0]["status"] == "active"

    prices = client.get(f"/api/v1/products/{product_id}/prices?range=30d").json()
    assert prices == []

    duplicate = client.post("/api/v1/products", json=product_payload())
    assert duplicate.status_code == 409

    assert client.delete(f"/api/v1/products/{product_id}").status_code == 204
    assert client.get(f"/api/v1/products/{product_id}").status_code == 404


def test_products_list_and_jobs(client):
    assert client.get("/api/v1/products").json() == []
    assert client.get("/api/v1/jobs").json() == []
    status = client.get("/api/v1/notifications/status")
    assert status.status_code == 200
    assert isinstance(status.json()["serverchan_configured"], bool)


def test_rejects_non_official_shop(client):
    payload = product_payload()
    payload["listing"]["shop_type"] = "other"

    response = client.post("/api/v1/products", json=payload)

    assert response.status_code == 422
    assert "官方" in response.json()["detail"]


def test_rejects_brand_mismatch(client):
    payload = product_payload()
    payload["listing"]["shop_type"] = "official_flagship"
    payload["listing"]["shop_name"] = "vivo官方旗舰店"
    payload["listing"]["title"] = "vivo X200 12GB+256GB"
    payload["listing"]["shop_evidence"] = {
        "official_badge": "true",
        "shop_brand": "vivo",
    }

    response = client.post("/api/v1/products", json=payload)

    assert response.status_code == 422
