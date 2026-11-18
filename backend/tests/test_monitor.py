from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.adapters.base import PriceQuote
from app.core.db import session_scope
from app.core.exceptions import CaptchaRequired, LoginRequired, ParseError, RateLimited
from app.core.models import (
    Account,
    JobRun,
    Listing,
    Notification,
    PriceSnapshot,
    ProductPriceSnapshot,
)
from app.core.price_engine import save_price_snapshot
from app.services.monitor import (
    _fetch_listing_quote,
    _hold_unconfirmed_jd_drop,
    _maybe_pause_after_failures,
    _poll_product,
)


@pytest.fixture(autouse=True)
def fake_edge_bridge(monkeypatch):
    async def fetch(listing):
        from app.services import monitor

        return await monitor.get_adapter("jd").fetch_page_price(listing, None)

    monkeypatch.setattr("app.services.monitor.edge_bridge.fetch", fetch)


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


async def test_taobao_degraded_extension_does_not_replace_valid_direct_quote(monkeypatch):
    class DirectAdapter:
        async def fetch_page_price(self, listing, account):
            return PriceQuote(
                "taobao", listing.id, "page", 269900,
                confidence="low", status="ok", page_price_cents=269900,
            )

    async def degraded_extension(listing):
        return PriceQuote(
            "taobao", listing.id, "page", 0,
            status="parse_error", error="淘宝页面处于访问异常/降级状态",
        )

    monkeypatch.setattr("app.services.monitor.edge_bridge.connected", lambda _: True)
    monkeypatch.setattr("app.services.monitor.edge_bridge.fetch", degraded_extension)
    quote = await _fetch_listing_quote(
        Listing(id=5, platform="taobao"),
        Account(platform="taobao", status="logged_in"),
        DirectAdapter(),
    )
    assert quote.status == "ok"
    assert quote.effective_price_cents == 269900
    assert quote.confidence == "low"
    assert "未更新价格" in quote.error


async def test_taobao_degraded_page_does_not_auto_pause():
    listing = Listing(id=5, platform="taobao", status="active")
    await _maybe_pause_after_failures(None, listing, "淘宝页面处于访问异常/降级状态")
    assert listing.status == "active"


async def test_taobao_reports_both_failed_capture_paths(monkeypatch):
    class BlockedAdapter:
        async def fetch_page_price(self, listing, account):
            raise LoginRequired("安全验证")

    async def degraded_extension(listing):
        return PriceQuote(
            "taobao", listing.id, "page", 0, status="parse_error",
            error="淘宝页面处于访问异常/降级状态",
        )

    monkeypatch.setattr("app.services.monitor.edge_bridge.connected", lambda _: True)
    monkeypatch.setattr("app.services.monitor.edge_bridge.fetch", degraded_extension)
    quote = await _fetch_listing_quote(
        Listing(id=5, platform="taobao"),
        Account(platform="taobao", status="logged_in"),
        BlockedAdapter(),
    )
    assert quote.status == "parse_error"
    assert "安全验证" in quote.error
    assert "访问异常/降级" in quote.error


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


def test_extreme_jd_page_drop_never_becomes_trusted_from_repetition(client):
    product_id = _create_product(client)
    with session_scope() as db:
        listing = db.scalars(
            select(Listing).where(Listing.product_id == product_id)
        ).one()
        save_price_snapshot(
            db,
            listing,
            PriceQuote("jd", listing.id, "page", 394348, confidence="high"),
        )
        first = PriceQuote("jd", listing.id, "page", 194946, confidence="high")
        _hold_unconfirmed_jd_drop(db, listing, first)
        assert first.confidence == "low"
        save_price_snapshot(db, listing, first)
        second = PriceQuote("jd", listing.id, "page", 194946, confidence="high")
        _hold_unconfirmed_jd_drop(db, listing, second)
        assert second.confidence == "low"


async def test_low_confidence_link_price_does_not_enter_product_history(client, monkeypatch):
    product_id = _create_product(client)
    with session_scope() as db:
        listing = db.scalars(select(Listing).where(Listing.product_id == product_id)).one()
        listing.shop_verified = False
        db.commit()

    confidence = "low"

    async def fetch(listing):
        return PriceQuote(
            platform="jd", listing_id=listing.id, source="page",
            effective_price_cents=394348, confidence=confidence, status="ok",
        )

    monkeypatch.setattr("app.services.monitor.edge_bridge.fetch", fetch)
    for _ in range(3):
        await _poll_product(product_id)
    with session_scope() as db:
        listing = db.scalars(select(Listing).where(Listing.product_id == product_id)).one()
        assert listing.status == "active"
        assert listing.shop_verified is False
        assert all(row.confidence == "low" for row in listing.price_snapshots)
        assert db.scalars(select(ProductPriceSnapshot)).all() == []

    confidence = "high"
    await _poll_product(product_id)
    with session_scope() as db:
        listing = db.scalars(select(Listing).where(Listing.product_id == product_id)).one()
        assert listing.shop_verified is True
        assert db.scalars(select(ProductPriceSnapshot)).one().lowest_price_cents == 394348


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


class RateLimitedAdapter:
    platform = "jd"

    async def fetch_page_price(self, listing, account):
        raise RateLimited("京东 PC 商品页频控")


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

    for _ in range(3):
        await _poll_product(product_id)

    with session_scope() as db:
        listing = db.scalars(select(Listing)).first()
        notifications = db.scalars(select(Notification)).all()

    assert listing is not None
    assert listing.status == "paused"
    assert notifications == []


async def test_pc_rate_limit_keeps_listing_scheduled(client, monkeypatch):
    client.get("/api/v1/accounts")
    product_id = _create_product(client)
    with session_scope() as db:
        account = db.scalars(select(Account).where(Account.platform == "jd")).first()
        assert account is not None
        account.status = "logged_in"
        db.commit()

    monkeypatch.setattr(
        "app.services.monitor.get_adapter",
        lambda platform: RateLimitedAdapter(),
    )

    for _ in range(3):
        await _poll_product(product_id)

    with session_scope() as db:
        listing = db.scalars(select(Listing)).first()
        snapshots = db.scalars(select(PriceSnapshot)).all()
        product_snapshots = db.scalars(select(ProductPriceSnapshot)).all()

    assert listing is not None
    assert listing.status == "active"
    assert len(snapshots) == 3
    assert all(snapshot.status == "rate_limited" for snapshot in snapshots)
    assert product_snapshots == []


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


async def test_paused_product_does_not_poll_until_reenabled(client, monkeypatch):
    client.get("/api/v1/accounts")
    product_id = _create_product(client)
    with session_scope() as db:
        account = db.scalars(select(Account).where(Account.platform == "jd")).one()
        account.status = "logged_in"
        db.commit()
    monkeypatch.setattr("app.services.monitor.get_adapter", lambda _: FakeAdapter())

    client.patch(f"/api/v1/products/{product_id}/monitoring", json={"enabled": False})
    await _poll_product(product_id)
    with session_scope() as db:
        assert db.scalars(select(JobRun)).all() == []
        assert db.scalars(select(PriceSnapshot)).all() == []

    client.patch(f"/api/v1/products/{product_id}/monitoring", json={"enabled": True})
    await _poll_product(product_id)
    with session_scope() as db:
        assert len(db.scalars(select(JobRun)).all()) == 1
        assert len(db.scalars(select(ProductPriceSnapshot)).all()) == 1


async def test_taobao_captcha_uses_edge_in_same_poll_then_retries_direct(client, monkeypatch):
    client.get("/api/v1/accounts")
    response = client.post(
        "/api/v1/products",
        json={
            "name": "iQOO Neo11 12GB+256GB",
            "brand": "iQOO",
            "model": "Neo11",
            "variant": "",
            "ram_gb": 12,
            "storage_gb": 256,
            "listing": {
                "platform": "taobao",
                "url": "https://detail.tmall.com/item.htm?id=824950233983",
                "title": "iQOO Neo11 12GB+256GB",
                "shop_name": "iQOO手机官方旗舰店",
                "shop_type": "official_flagship",
                "platform_item_id": "824950233983",
                "platform_sku_id": "4403221617613",
                "shop_evidence": {"official_badge": "true", "shop_brand": "iQOO"},
                "detected_specs": {"ram_gb": "12", "storage_gb": "256"},
            },
        },
    )
    assert response.status_code == 200
    product_id = response.json()["id"]
    with session_scope() as db:
        account = db.scalars(select(Account).where(Account.platform == "taobao")).one()
        account.status = "logged_in"
        db.commit()

    calls = {"primary": 0, "edge": 0}

    class CaptchaTaobaoAdapter:
        async def fetch_page_price(self, listing, account):
            calls["primary"] += 1
            raise CaptchaRequired("淘宝触发验证")

    async def edge_fetch(listing):
        calls["edge"] += 1
        return PriceQuote(
            platform="taobao",
            listing_id=listing.id,
            source="page",
            confidence="high",
            effective_price_cents=319410,
            page_price_cents=439900,
            estimated_price_cents=319410,
        )

    monkeypatch.setattr("app.services.monitor.get_adapter", lambda _: CaptchaTaobaoAdapter())
    monkeypatch.setattr("app.services.monitor.edge_bridge.fetch", edge_fetch)
    monkeypatch.setattr("app.services.monitor.edge_bridge.connected", lambda _: True)

    await _poll_product(product_id)
    assert calls == {"primary": 1, "edge": 1}
    with session_scope() as db:
        listing = db.scalars(select(Listing)).one()
        assert listing.status == "active"
        assert listing.capture_mode == "primary"
        snapshot = db.scalars(select(ProductPriceSnapshot)).one()
        assert snapshot.lowest_price_cents == 319410

    await _poll_product(product_id)
    assert calls == {"primary": 2, "edge": 2}
    with session_scope() as db:
        listing = db.scalars(select(Listing)).one()
        assert listing.capture_mode == "primary"


async def test_taobao_direct_success_does_not_open_edge(client, monkeypatch):
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
    assert client.post(f"/api/v1/products/{product_id}/listings", json=listing).status_code == 200
    with session_scope() as db:
        db.scalars(select(Account).where(Account.platform == "taobao")).one().status = "logged_in"
        db.scalars(select(Listing).where(Listing.platform == "jd")).one().status = "paused"
        db.commit()

    calls = {"primary": 0, "edge": 0}

    class DirectTaobaoAdapter:
        async def fetch_page_price(self, item, account):
            calls["primary"] += 1
            return PriceQuote("taobao", item.id, "page", 319410, confidence="high")

    async def edge_fetch(item):
        calls["edge"] += 1
        raise AssertionError("Edge should not run after a successful direct capture")

    monkeypatch.setattr("app.services.monitor.get_adapter", lambda _: DirectTaobaoAdapter())
    monkeypatch.setattr("app.services.monitor.edge_bridge.fetch", edge_fetch)
    monkeypatch.setattr("app.services.monitor.random.uniform", lambda lower, upper: 0)
    await _poll_product(product_id)
    assert calls == {"primary": 1, "edge": 0}


async def test_taobao_failed_quote_uses_edge_in_same_poll(client, monkeypatch):
    client.get("/api/v1/accounts")
    product_id = client.post("/api/v1/products", json={
        "name": "iQOO Neo11 12GB+256GB", "brand": "iQOO", "model": "Neo11",
        "variant": "", "ram_gb": 12, "storage_gb": 256,
        "listing": {
            "platform": "taobao",
            "url": "https://detail.tmall.com/item.htm?id=824950233983",
            "title": "iQOO Neo11 12GB+256GB",
            "shop_name": "iQOO手机官方旗舰店",
            "shop_type": "official_flagship",
            "platform_item_id": "824950233983",
            "platform_sku_id": "4403221617613",
            "shop_evidence": {"official_badge": "true", "shop_brand": "iQOO"},
            "detected_specs": {"ram_gb": "12", "storage_gb": "256"},
        },
    }).json()["id"]
    with session_scope() as db:
        db.scalars(select(Account).where(Account.platform == "taobao")).one().status = "logged_in"
        db.commit()

    calls = {"primary": 0, "edge": 0}

    class DegradedTaobaoAdapter:
        async def fetch_page_price(self, item, account):
            calls["primary"] += 1
            return PriceQuote("taobao", item.id, "page", 0, status="parse_error", error="页面结构变化")

    async def edge_fetch(item):
        calls["edge"] += 1
        return PriceQuote("taobao", item.id, "page", 319410, confidence="high")

    monkeypatch.setattr("app.services.monitor.get_adapter", lambda _: DegradedTaobaoAdapter())
    monkeypatch.setattr("app.services.monitor.edge_bridge.fetch", edge_fetch)
    monkeypatch.setattr("app.services.monitor.edge_bridge.connected", lambda _: True)
    await _poll_product(product_id)
    assert calls == {"primary": 1, "edge": 1}
    with session_scope() as db:
        assert db.scalars(select(ProductPriceSnapshot)).one().lowest_price_cents == 319410
