from datetime import UTC, datetime

from sqlalchemy import select

from app.core.db import session_scope
from app.core.models import JobRun, Listing, PriceSnapshot, Product, ProductPriceSnapshot
from app.core.price_engine import previous_low_cents


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


def test_user_can_create_named_product_without_phone_specs_or_links(client):
    first = client.post("/api/v1/products", json={"name": "书桌台灯"})
    second = client.post("/api/v1/products", json={"name": "书桌台灯"})
    assert first.status_code == second.status_code == 200
    assert first.json()["id"] != second.json()["id"]
    assert first.json()["listing_count"] == 0
    assert first.json()["status"] == "empty"
    assert first.json()["history_low_cents"] is None


def test_two_links_in_same_shop_keep_separate_curves_and_shared_low(client):
    product_id = client.post("/api/v1/products", json={"name": "客厅灯"}).json()["id"]
    base = product_payload()["listing"]
    first = {**base, "platform_item_id": "111", "url": "https://item.jd.com/111.html",
             "shop_name": "普通灯具店", "shop_type": "other"}
    second = {**first, "platform_item_id": "222", "url": "https://item.jd.com/222.html"}
    for item in (first, second):
        assert client.post(f"/api/v1/products/{product_id}/listings", json=item).status_code == 200
    with session_scope() as db:
        listings = db.scalars(select(Listing).where(Listing.product_id == product_id)).all()
        db.add_all([
            PriceSnapshot(listing_id=listings[0].id, source="page", status="ok",
                          confidence="high", effective_price_cents=26900),
            PriceSnapshot(listing_id=listings[1].id, source="page", status="ok",
                          confidence="high", effective_price_cents=24900),
        ])
        db.commit()
    detail = client.get(f"/api/v1/products/{product_id}").json()
    assert detail["history_low_cents"] == 24900
    assert detail["current_price_cents"] == 24900
    assert detail["history_low_platform"] == "jd"
    assert detail["history_low_shop_name"] == "普通灯具店"
    curves = client.get(f"/api/v1/products/{product_id}/listing-prices?range=all").json()
    assert len(curves) == 2
    assert len({series["listing_id"] for series in curves}) == 2


def test_existing_implausible_page_quote_is_excluded_from_prices_and_history(client):
    product_id = client.post("/api/v1/products", json=product_payload()).json()["id"]
    with session_scope() as db:
        listing = db.scalars(select(Listing).where(Listing.product_id == product_id)).one()
        db.add(PriceSnapshot(
            listing_id=listing.id, source="page", status="ok", confidence="high",
            page_price_cents=333900, effective_price_cents=9000,
        ))
        db.add(ProductPriceSnapshot(
            product_id=product_id, lowest_listing_id=listing.id,
            lowest_platform="jd", lowest_price_cents=9000,
        ))
        db.commit()
    detail = client.get(f"/api/v1/products/{product_id}").json()
    assert detail["current_price_cents"] is None
    assert detail["history_low_cents"] is None
    assert detail["listings"][0]["effective_price_cents"] is None
    assert detail["listings"][0]["last_attempt_status"] == "low_confidence"
    assert "远低于" in detail["listings"][0]["last_attempt_error"]
    assert client.get(f"/api/v1/products/{product_id}/prices?range=all").json() == []
    assert client.get(f"/api/v1/products/{product_id}/listing-prices?range=all").json() == []
    with session_scope() as db:
        assert previous_low_cents(db, product_id) is None


def test_create_list_detail_delete_product(client):
    response = client.post("/api/v1/products", json=product_payload())

    assert response.status_code == 200
    summary = response.json()
    assert summary["name"] == "iQOO Neo11 至尊版 12GB+512GB"
    assert summary["current_price_cents"] is None
    assert summary["history_low_cents"] is None
    assert summary["status"] == "active"
    assert summary["monitoring_enabled"] is True
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


def test_product_monitoring_pause_resume_preserves_listing_statuses(client):
    product_id = client.post("/api/v1/products", json=product_payload()).json()["id"]
    with session_scope() as db:
        listing_id = db.scalars(select(Listing).where(Listing.product_id == product_id)).one().id

    paused = client.patch(
        f"/api/v1/products/{product_id}/monitoring", json={"enabled": False}
    )
    assert paused.status_code == 200
    assert paused.json()["monitoring_enabled"] is False
    assert paused.json()["status"] == "paused"
    assert client.post(f"/api/v1/products/{product_id}/refresh").status_code == 409
    assert client.get("/api/v1/products").json()[0]["status"] == "paused"
    assert client.get(f"/api/v1/products/{product_id}").json()["listings"][0]["status"] == "active"

    assert client.patch(f"/api/v1/listings/{listing_id}", json={"status": "paused"}).status_code == 200
    resumed = client.patch(
        f"/api/v1/products/{product_id}/monitoring", json={"enabled": True}
    )
    assert resumed.status_code == 200
    assert resumed.json()["monitoring_enabled"] is True
    assert resumed.json()["status"] == "paused"
    assert client.get(f"/api/v1/products/{product_id}").json()["listings"][0]["status"] == "paused"
    assert client.post(f"/api/v1/products/{product_id}/refresh").status_code == 409

    assert client.patch(f"/api/v1/listings/{listing_id}", json={"status": "active"}).status_code == 200
    assert client.get(f"/api/v1/products/{product_id}").json()["status"] == "active"


def test_product_monitoring_rejects_invalid_payload(client):
    product_id = client.post("/api/v1/products", json=product_payload()).json()["id"]
    response = client.patch(
        f"/api/v1/products/{product_id}/monitoring", json={"enabled": "later"}
    )
    assert response.status_code == 422


def test_batch_adds_two_platforms_to_one_user_product(client):
    jd = product_payload()["listing"]
    taobao = {
        **jd, "platform": "taobao",
        "url": "https://detail.tmall.com/item.htm?id=200&skuId=201",
        "shop_name": "iQOO手机官方旗舰店",
        "shop_type": "official_flagship",
        "platform_item_id": "200", "platform_sku_id": "201",
        "shop_evidence": {"official_badge": "true", "shop_brand": "iQOO"},
    }
    payload = product_payload()
    payload.pop("listing")
    payload["listings"] = [jd, taobao]
    first = client.post("/api/v1/products/batch", json=payload)
    assert first.status_code == 200
    assert first.json()["listing_count"] == 2
    second = client.post("/api/v1/products/batch", json=payload)
    assert second.status_code == 409
    assert len(client.get("/api/v1/products").json()) == 1


def test_batch_accepts_ordinary_shop(client):
    payload = product_payload()
    valid = payload.pop("listing")
    payload["listings"] = [valid, {**valid, "platform_item_id": "999",
                                   "shop_name": "普通手机专营店", "shop_type": "other"}]
    response = client.post("/api/v1/products/batch", json=payload)
    assert response.status_code == 200
    assert response.json()["listing_count"] == 2


def test_delete_product_removes_listings_and_price_history(client):
    product_id = client.post("/api/v1/products", json=product_payload()).json()["id"]
    with session_scope() as db:
        listing = db.scalars(select(Listing).where(Listing.product_id == product_id)).one()
        db.add(PriceSnapshot(
            listing_id=listing.id,
            source="page",
            effective_price_cents=394348,
            status="ok",
        ))
        db.add(ProductPriceSnapshot(
            product_id=product_id,
            lowest_price_cents=394348,
            lowest_platform="jd",
            lowest_listing_id=listing.id,
        ))
        db.add(JobRun(
            platform="jd",
            listing_id=listing.id,
            job_type="page_price",
            status="ok",
        ))
        db.commit()

    assert client.delete(f"/api/v1/products/{product_id}").status_code == 204
    assert client.get("/api/v1/products").json() == []
    with session_scope() as db:
        assert db.scalars(select(Listing)).all() == []
        assert db.scalars(select(PriceSnapshot)).all() == []
        assert db.scalars(select(ProductPriceSnapshot)).all() == []
        assert db.scalars(select(JobRun)).one().listing_id is None


def test_multi_store_price_history_and_global_low_provenance(client):
    product_id = client.post("/api/v1/products", json=product_payload()).json()["id"]
    taobao_listing = {
        **product_payload()["listing"],
        "platform": "taobao",
        "url": "https://detail.tmall.com/item.htm?id=200&skuId=201",
        "shop_name": "iQOO手机官方旗舰店",
        "shop_type": "official_flagship",
        "platform_item_id": "200",
        "platform_sku_id": "201",
        "shop_evidence": {"official_badge": "true", "shop_brand": "iQOO"},
    }
    assert client.post(f"/api/v1/products/{product_id}/listings", json=taobao_listing).status_code == 200
    with session_scope() as db:
        product = db.get(Product, product_id)
        jd = next(item for item in product.listings if item.platform == "jd")
        tb = next(item for item in product.listings if item.platform == "taobao")
        db.add_all([
            PriceSnapshot(listing_id=jd.id, source="page", status="ok", effective_price_cents=394348),
            PriceSnapshot(listing_id=tb.id, source="page", status="ok", effective_price_cents=389900),
            ProductPriceSnapshot(product_id=product_id, lowest_price_cents=389900,
                                 lowest_platform="taobao", lowest_listing_id=tb.id),
        ])
        db.commit()

    detail = client.get(f"/api/v1/products/{product_id}").json()
    assert detail["page_low_cents"] == 389900
    assert detail["page_low_platform"] == "taobao"
    assert detail["page_low_shop_name"] == "iQOO手机官方旗舰店"
    assert detail["history_low_platform"] == "taobao"
    curves = client.get(f"/api/v1/products/{product_id}/listing-prices?range=all").json()
    assert {item["shop_name"] for item in curves} == {"iQOO京东自营旗舰店", "iQOO手机官方旗舰店"}


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
    assert detail["listings"][0]["last_attempt_status"] == "low_confidence"
    assert "未采纳" in detail["listings"][0]["last_attempt_error"]
    assert client.get(
        f"/api/v1/products/{product_id}/listing-prices?range=30d"
    ).json() == []


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
    accepted = client.post(f"/api/v1/products/{product_id}/listings", json=listing)
    assert accepted.status_code == 200
    assert accepted.json()["listing_count"] == 3


def test_accepts_non_official_shop(client):
    payload = product_payload()
    payload["listing"]["shop_type"] = "other"

    response = client.post("/api/v1/products", json=payload)

    assert response.status_code == 200
    assert response.json()["listing_count"] == 1


def test_accepts_user_selected_link_with_different_brand(client):
    payload = product_payload()
    payload["listing"]["shop_type"] = "official_flagship"
    payload["listing"]["shop_name"] = "vivo官方旗舰店"
    payload["listing"]["title"] = "vivo X200 12GB+256GB"
    payload["listing"]["shop_evidence"] = {
        "official_badge": "true",
        "shop_brand": "vivo",
    }

    response = client.post("/api/v1/products", json=payload)

    assert response.status_code == 200
