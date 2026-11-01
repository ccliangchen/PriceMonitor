from datetime import UTC, datetime

from sqlalchemy import select

from app.core.db import session_scope
from app.core.models import PriceSnapshot, Product


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


def test_pause_and_resume_listing(client):
    product_id = client.post("/api/v1/products", json=product_payload()).json()["id"]
    with session_scope() as db:
        product = db.get(Product, product_id)
        listing_id = product.listings[0].id
        db.add(
            PriceSnapshot(
                listing_id=listing_id,
                captured_at=datetime.now(UTC),
                source="page",
                effective_price_cents=0,
                status="parse_error",
                error_message="解析失败",
            )
        )
        db.commit()

    paused = client.patch(f"/api/v1/listings/{listing_id}", json={"status": "paused"})
    assert paused.status_code == 200
    assert paused.json()["status"] == "paused"

    resumed = client.patch(f"/api/v1/listings/{listing_id}", json={"status": "active"})
    assert resumed.status_code == 200
    assert resumed.json()["status"] == "active"

    with session_scope() as db:
        failures = db.scalars(
            select(PriceSnapshot).where(PriceSnapshot.status != "ok")
        ).all()
    assert failures == []


def test_listing_price_series(client):
    product_id = client.post("/api/v1/products", json=product_payload()).json()["id"]
    listing = {
        "platform": "taobao",
        "url": "https://detail.tmall.com/item.htm?id=824950233983",
        "title": "iQOO Neo11 至尊版 12GB+512GB",
        "shop_name": "iQOO手机官方旗舰店",
        "shop_type": "official_flagship",
        "platform_item_id": "824950233983",
        "platform_sku_id": "4403221617613",
        "shop_evidence": {"official_badge": "true", "shop_brand": "iQOO"},
        "detected_specs": {"ram_gb": "12", "storage_gb": "512"},
    }
    client.post(f"/api/v1/products/{product_id}/listings", json=listing)

    with session_scope() as db:
        product = db.get(Product, product_id)
        for item in product.listings:
            for cents in (399900, 389900):
                db.add(
                    PriceSnapshot(
                        listing_id=item.id,
                        captured_at=datetime.now(UTC),
                        source="page",
                        page_price_cents=cents,
                        estimated_price_cents=cents,
                        effective_price_cents=cents,
                        status="ok",
                    )
                )
        db.commit()

    response = client.get(
        f"/api/v1/products/{product_id}/listing-prices?range=30d"
    )

    assert response.status_code == 200
    series = response.json()
    assert [item["platform"] for item in series] == ["jd", "taobao"]
    assert all(len(item["points"]) == 2 for item in series)
    assert series[0]["points"][0]["effective_price_cents"] == 399900


def test_summary_separates_page_and_checkout_lows(client):
    product_id = client.post("/api/v1/products", json=product_payload()).json()["id"]
    with session_scope() as db:
        product = db.get(Product, product_id)
        listing_id = product.listings[0].id
        for source, cents, confidence in (
            ("page", 319410, "high"),
            ("page", 299900, "low"),
            ("checkout", 369900, "high"),
        ):
            db.add(
                PriceSnapshot(
                    listing_id=listing_id,
                    captured_at=datetime.now(UTC),
                    source=source,
                    confidence=confidence,
                    page_price_cents=439900,
                    estimated_price_cents=319410,
                    checkout_price_cents=cents if source == "checkout" else None,
                    effective_price_cents=cents,
                    status="ok",
                )
            )
        db.commit()

    summary = client.get(f"/api/v1/products/{product_id}").json()

    assert summary["page_low_cents"] == 319410
    assert summary["checkout_low_cents"] == 369900
    assert summary["checkout_last_at"] is not None


def test_low_confidence_price_is_not_exposed(client):
    product_id = client.post("/api/v1/products", json=product_payload()).json()["id"]
    with session_scope() as db:
        product = db.get(Product, product_id)
        db.add(
            PriceSnapshot(
                listing_id=product.listings[0].id,
                captured_at=datetime.now(UTC),
                source="page",
                confidence="low",
                page_price_cents=299900,
                estimated_price_cents=299900,
                effective_price_cents=299900,
                status="ok",
            )
        )
        db.commit()

    detail = client.get(f"/api/v1/products/{product_id}").json()

    assert detail["current_price_cents"] is None
    assert detail["listings"][0]["effective_price_cents"] is None
    assert detail["listings"][0]["price_confidence"] is None


def test_products_list_and_jobs(client):
    assert client.get("/api/v1/products").json() == []
    assert client.get("/api/v1/jobs").json() == []
    status = client.get("/api/v1/notifications/status")
    assert status.status_code == 200
    assert isinstance(status.json()["serverchan_configured"], bool)


def test_bind_second_platform_listing(client):
    product_id = client.post("/api/v1/products", json=product_payload()).json()["id"]
    listing = {
        "platform": "taobao",
        "url": "https://detail.tmall.com/item.htm?id=824950233983&skuId=4403221617613",
        "title": "iQOO Neo11 至尊版 12GB+512GB",
        "shop_name": "iQOO手机官方旗舰店",
        "shop_type": "official_flagship",
        "platform_item_id": "824950233983",
        "platform_sku_id": "4403221617613",
        "shop_evidence": {"official_badge": "true", "shop_brand": "iQOO"},
        "detected_specs": {"ram_gb": "12", "storage_gb": "512"},
    }

    response = client.post(f"/api/v1/products/{product_id}/listings", json=listing)

    assert response.status_code == 200
    detail = response.json()
    assert detail["listing_count"] == 2
    assert [item["platform"] for item in detail["listings"]] == ["jd", "taobao"]

    duplicate = client.post(f"/api/v1/products/{product_id}/listings", json=listing)
    assert duplicate.status_code == 409

    listing["shop_name"] = "某某数码专营店"
    listing["shop_type"] = "other"
    listing["platform_sku_id"] = "999"
    rejected = client.post(f"/api/v1/products/{product_id}/listings", json=listing)
    assert rejected.status_code == 422


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
