from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.adapters.base import PriceQuote
from app.core.db import session_scope
from app.core.models import (
    Account,
    Listing,
    Notification,
    PriceSnapshot,
    Product,
    ProductPriceSnapshot,
)
from app.services.checkout import (
    _run_checkout_calibration,
    effective_quotes,
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


def _add_snapshot(
    listing_id: int,
    source: str,
    cents: int,
    age: timedelta,
    confidence: str | None = None,
) -> None:
    with session_scope() as db:
        db.add(
            PriceSnapshot(
                listing_id=listing_id,
                captured_at=datetime.now(UTC) - age,
                source=source,
                confidence=confidence,
                page_price_cents=cents,
                estimated_price_cents=cents,
                checkout_price_cents=cents if source == "checkout" else None,
                effective_price_cents=cents,
                status="ok",
            )
        )
        db.commit()


def test_fresh_page_price_wins(client):
    product_id = _create_product(client)
    with session_scope() as db:
        product = db.get(Product, product_id)
        listing = product.listings[0]
        listing_id = listing.id

    _add_snapshot(listing_id, "page", 369800, timedelta(minutes=5))
    _add_snapshot(listing_id, "checkout", 359900, timedelta(hours=1))

    with session_scope() as db:
        product = db.get(Product, product_id)
        quotes = effective_quotes(db, product)

    assert len(quotes) == 1
    assert quotes[0][1].source == "page"
    assert quotes[0][1].effective_price_cents == 369800


def test_stale_page_falls_back_to_fresh_checkout(client):
    product_id = _create_product(client)
    with session_scope() as db:
        product = db.get(Product, product_id)
        listing_id = product.listings[0].id

    _add_snapshot(listing_id, "checkout", 359900, timedelta(hours=1))
    _add_snapshot(listing_id, "page", 369800, timedelta(hours=3))

    with session_scope() as db:
        product = db.get(Product, product_id)
        quotes = effective_quotes(db, product)

    assert len(quotes) == 1
    assert quotes[0][1].source == "checkout"
    assert quotes[0][1].effective_price_cents == 359900


def test_low_confidence_page_is_not_used(client):
    product_id = _create_product(client)
    with session_scope() as db:
        product = db.get(Product, product_id)
        listing_id = product.listings[0].id

    _add_snapshot(
        listing_id,
        "page",
        319900,
        timedelta(minutes=5),
        confidence="low",
    )
    _add_snapshot(
        listing_id,
        "checkout",
        369900,
        timedelta(hours=1),
        confidence="high",
    )

    with session_scope() as db:
        product = db.get(Product, product_id)
        quotes = effective_quotes(db, product)

    assert len(quotes) == 1
    assert quotes[0][1].source == "checkout"
    assert quotes[0][1].effective_price_cents == 369900


def test_stale_page_is_not_used(client):
    product_id = _create_product(client)
    with session_scope() as db:
        product = db.get(Product, product_id)
        listing_id = product.listings[0].id

    _add_snapshot(listing_id, "page", 369800, timedelta(hours=3))

    with session_scope() as db:
        product = db.get(Product, product_id)
        quotes = effective_quotes(db, product)

    assert quotes == []


class CheckoutAdapter:
    platform = "jd"

    async def fetch_checkout_price(self, listing, account, headless=False):
        return PriceQuote(
            platform="jd",
            listing_id=listing.id,
            source="checkout",
            effective_price_cents=349900,
            captured_at=datetime.now(UTC),
            checkout_price_cents=349900,
            status="ok",
        )


async def test_checkout_calibration_updates_product_snapshot(client, monkeypatch):
    client.get("/api/v1/accounts")
    _create_product(client)
    with session_scope() as db:
        account = db.scalars(
            select(Account).where(Account.platform == "jd")
        ).first()
        assert account is not None
        account.status = "logged_in"
        listing = db.scalars(select(Listing)).first()
        assert listing is not None
        listing_id = listing.id
        db.commit()

    monkeypatch.setattr(
        "app.services.checkout.get_adapter",
        lambda platform: CheckoutAdapter(),
    )
    _add_snapshot(listing_id, "page", 359900, timedelta(minutes=5))

    await _run_checkout_calibration(listing_id)

    with session_scope() as db:
        checkout = db.scalars(
            select(PriceSnapshot).where(PriceSnapshot.source == "checkout")
        ).first()
        product_snapshot = db.scalars(select(ProductPriceSnapshot)).first()
        listing = db.get(Listing, listing_id)

    assert checkout is not None
    assert checkout.checkout_price_cents == 349900
    assert checkout.page_price_cents == 359900
    assert product_snapshot is not None
    assert product_snapshot.lowest_price_cents == 359900
    assert product_snapshot.source_mix == {"jd": "page"}
    assert listing is not None
    assert listing.last_checked_at is not None


async def test_manual_checkout_new_low_notification(client, monkeypatch):
    client.get("/api/v1/accounts")
    _create_product(client)
    with session_scope() as db:
        account = db.scalars(
            select(Account).where(Account.platform == "jd")
        ).first()
        assert account is not None
        account.status = "logged_in"
        listing = db.scalars(select(Listing)).first()
        assert listing is not None
        listing_id = listing.id
        db.commit()

    _add_snapshot(listing_id, "checkout", 399900, timedelta(hours=2))
    _add_snapshot(listing_id, "page", 359900, timedelta(minutes=5))
    monkeypatch.setattr(
        "app.services.checkout.get_adapter",
        lambda platform: CheckoutAdapter(),
    )

    await _run_checkout_calibration(listing_id)

    with session_scope() as db:
        notification = db.scalars(select(Notification)).first()

    assert notification is not None
    assert notification.payload is not None
    assert "实付新低" in str(notification.payload.get("title"))


def test_checkout_snapshot_is_linked_to_listing(client):
    product_id = _create_product(client)
    with session_scope() as db:
        product = db.get(Product, product_id)
        listing_id = product.listings[0].id
    _add_snapshot(listing_id, "checkout", 359900, timedelta(minutes=1))

    with session_scope() as db:
        snapshot = db.scalars(select(PriceSnapshot)).first()

    assert snapshot is not None
    assert snapshot.source == "checkout"
    assert snapshot.checkout_price_cents == 359900
