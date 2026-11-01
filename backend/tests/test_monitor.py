from datetime import UTC, datetime

from sqlalchemy import select

from app.adapters.base import PriceQuote
from app.core.db import session_scope
from app.core.exceptions import ParseError
from app.core.models import Account, Listing, ProductPriceSnapshot
from app.services.monitor import _poll_product


class FakeAdapter:
    platform = "jd"

    async def fetch_page_price(self, listing, account):
        return PriceQuote(
            platform="jd",
            listing_id=listing.id,
            source="page",
            effective_price_cents=359900,
            captured_at=datetime.now(UTC),
            page_price_cents=359900,
            estimated_price_cents=359900,
            status="ok",
        )


class FakeTaobaoAdapter(FakeAdapter):
    platform = "taobao"

    async def fetch_page_price(self, listing, account):
        return PriceQuote(
            platform="taobao",
            listing_id=listing.id,
            source="page",
            effective_price_cents=349900,
            captured_at=datetime.now(UTC),
            page_price_cents=349900,
            estimated_price_cents=349900,
            status="ok",
        )


def _create_product(client) -> int:
    payload = {
        "name": "iQOO Neo11 12GB+256GB",
        "brand": "iQOO",
        "model": "Neo11",
        "variant": "",
        "ram_gb": 12,
        "storage_gb": 256,
        "color": None,
        "notes": None,
        "listing": {
            "platform": "jd",
            "url": "https://item.jd.com/100.html",
            "title": "iQOO Neo11 12GB+256GB",
            "shop_name": "iQOO京东自营旗舰店",
            "shop_type": "jd_official_self",
            "platform_item_id": "100",
            "platform_sku_id": None,
            "shop_evidence": {"self_operated": "true", "shop_brand": "iQOO"},
            "detected_specs": {"ram_gb": "12", "storage_gb": "256"},
        },
    }
    return client.post("/api/v1/products", json=payload).json()["id"]


async def test_poll_product_uses_lowest_across_platforms(client, monkeypatch):
    client.get("/api/v1/accounts")
    product_id = _create_product(client)
    listing = {
        "platform": "taobao",
        "url": "https://detail.tmall.com/item.htm?id=824950233983",
        "title": "iQOO Neo11 12GB+256GB",
        "shop_name": "iQOO手机官方旗舰店",
        "shop_type": "official_flagship",
        "platform_item_id": "824950233983",
        "platform_sku_id": "4403221617613",
        "shop_evidence": {"official_badge": "true", "shop_brand": "iQOO"},
        "detected_specs": {"ram_gb": "12", "storage_gb": "256"},
    }
    bound = client.post(f"/api/v1/products/{product_id}/listings", json=listing)
    assert bound.status_code == 200

    with session_scope() as db:
        for account in db.scalars(select(Account)).all():
            account.status = "logged_in"
        db.commit()

    adapters = {"jd": FakeAdapter(), "taobao": FakeTaobaoAdapter()}
    monkeypatch.setattr(
        "app.services.monitor.get_adapter",
        lambda platform: adapters[platform],
    )
    monkeypatch.setattr(
        "app.services.monitor.random.uniform",
        lambda lower, upper: 0,
    )

    await _poll_product(product_id)

    with session_scope() as db:
        snapshot = db.scalars(select(ProductPriceSnapshot)).first()

    assert snapshot is not None
    assert snapshot.lowest_price_cents == 349900
    assert snapshot.lowest_platform == "taobao"
    assert snapshot.coverage == {"jd": "ok", "taobao": "ok"}


class LowConfidenceAdapter(FakeAdapter):
    platform = "jd"

    async def fetch_page_price(self, listing, account):
        return PriceQuote(
            platform="jd",
            listing_id=listing.id,
            source="page",
            confidence="low",
            effective_price_cents=299900,
            captured_at=datetime.now(UTC),
            page_price_cents=299900,
            estimated_price_cents=299900,
            status="ok",
        )


class FailingAdapter:
    platform = "jd"

    async def fetch_page_price(self, listing, account):
        raise ParseError("页面结构变化")


async def test_three_consecutive_failures_pause_listing(client, monkeypatch):
    client.get("/api/v1/accounts")
    product_id = _create_product(client)
    with session_scope() as db:
        account = db.scalars(
            select(Account).where(Account.platform == "jd")
        ).first()
        assert account is not None
        account.status = "logged_in"
        db.commit()

    monkeypatch.setattr(
        "app.services.monitor.get_adapter",
        lambda platform: FailingAdapter(),
    )

    async def no_alert(*args, **kwargs):
        return None

    monkeypatch.setattr(
        "app.services.monitor.send_listing_paused_alert",
        no_alert,
    )

    for _ in range(3):
        await _poll_product(product_id)

    with session_scope() as db:
        listing = db.scalars(select(Listing)).first()

    assert listing is not None
    assert listing.status == "paused"


async def test_low_confidence_quote_is_not_used_for_product_snapshot(client, monkeypatch):
    client.get("/api/v1/accounts")
    product_id = _create_product(client)
    with session_scope() as db:
        account = db.scalars(
            select(Account).where(Account.platform == "jd")
        ).first()
        assert account is not None
        account.status = "logged_in"
        db.commit()

    monkeypatch.setattr(
        "app.services.monitor.get_adapter",
        lambda platform: LowConfidenceAdapter(),
    )

    await _poll_product(product_id)

    with session_scope() as db:
        product_snapshots = db.scalars(select(ProductPriceSnapshot)).all()
        listing = db.scalars(select(Listing)).first()

    assert product_snapshots == []
    assert listing is not None
    assert listing.last_checked_at is not None


async def test_poll_product_records_product_snapshot(client, monkeypatch):
    client.get("/api/v1/accounts")
    product_id = _create_product(client)
    with session_scope() as db:
        account = db.scalars(
            select(Account).where(Account.platform == "jd")
        ).first()
        assert account is not None
        account.status = "logged_in"
        db.commit()

    monkeypatch.setattr(
        "app.services.monitor.get_adapter",
        lambda platform: FakeAdapter(),
    )

    await _poll_product(product_id)

    with session_scope() as db:
        snapshot = db.scalars(select(ProductPriceSnapshot)).first()
        listing = db.scalars(select(Listing)).first()

    assert snapshot is not None
    assert snapshot.lowest_price_cents == 359900
    assert snapshot.lowest_platform == "jd"
    assert listing is not None
    assert listing.last_checked_at is not None
    assert listing.status == "active"
