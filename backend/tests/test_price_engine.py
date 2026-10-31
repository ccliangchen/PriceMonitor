from datetime import UTC, datetime

from app.adapters.base import PriceQuote
from app.core.db import dispose_db, init_db, session_scope
from app.core.models import Listing, Product
from app.core.price_engine import (
    compute_lowest,
    history_low_cents,
    is_new_low,
    record_product_snapshot,
    save_price_snapshot,
)


def make_product() -> Product:
    return Product(
        name="iQOO Neo11 至尊版 12GB+512GB",
        brand="iQOO",
        model="Neo11",
        variant="至尊版",
        ram_gb=12,
        storage_gb=512,
        canonical_key="iqoo|neo11|至尊版|12|512|",
    )


def make_listing(product: Product) -> Listing:
    return Listing(
        product=product,
        platform="jd",
        shop_name="iQOO京东自营旗舰店",
        shop_type="jd_official_self",
        shop_verified=True,
        url="https://item.jd.com/100.html",
        platform_item_id="100",
        title="iQOO Neo11 至尊版 12GB+512GB",
        status="active",
    )


def make_quote(listing_id: int, cents: int, status: str = "ok") -> PriceQuote:
    return PriceQuote(
        platform="jd",
        listing_id=listing_id,
        source="page",
        effective_price_cents=cents,
        page_price_cents=cents,
        estimated_price_cents=cents,
        captured_at=datetime.now(UTC),
        status=status,  # type: ignore[arg-type]
    )


def test_first_snapshot_is_baseline_not_new_low(tmp_path):
    init_db(tmp_path)
    with session_scope() as db:
        product = make_product()
        listing = make_listing(product)
        db.add(product)
        db.add(listing)
        db.commit()
        db.refresh(product)
        db.refresh(listing)

        snapshot, new_low, previous = record_product_snapshot(
            db, product, [(listing, make_quote(listing.id, 749900))]
        )

        assert snapshot.lowest_price_cents == 749900
        assert snapshot.previous_low_cents is None
        assert new_low is False
        assert previous is None
        assert history_low_cents(db, product.id) == 749900

    dispose_db()


def test_lower_price_is_new_low_and_higher_is_not(tmp_path):
    init_db(tmp_path)
    with session_scope() as db:
        product = make_product()
        listing = make_listing(product)
        db.add(product)
        db.add(listing)
        db.commit()
        db.refresh(product)
        db.refresh(listing)

        record_product_snapshot(db, product, [(listing, make_quote(listing.id, 749900))])
        lower, lower_is_new, lower_previous = record_product_snapshot(
            db, product, [(listing, make_quote(listing.id, 729900))]
        )
        higher, higher_is_new, higher_previous = record_product_snapshot(
            db, product, [(listing, make_quote(listing.id, 739900))]
        )

        assert lower_is_new is True
        assert lower_previous == 749900
        assert lower.lowest_price_cents == 729900
        assert higher_is_new is False
        assert higher_previous == 729900
        assert history_low_cents(db, product.id) == 729900

    dispose_db()


def test_hysteresis_ignores_tiny_drop():
    assert is_new_low(99900, 100000) is False
    assert is_new_low(99899, 100000) is True
    assert is_new_low(100, None) is False


def test_invalid_quotes_are_ignored(tmp_path):
    init_db(tmp_path)
    with session_scope() as db:
        product = make_product()
        listing = make_listing(product)
        db.add(product)
        db.add(listing)
        db.commit()
        db.refresh(product)
        db.refresh(listing)

        saved = save_price_snapshot(db, listing, make_quote(listing.id, 0, "parse_error"))
        assert saved.status == "parse_error"

        result = compute_lowest(
            [
                (listing, make_quote(listing.id, 0, "parse_error")),
                (listing, make_quote(listing.id, 749900)),
            ]
        )
        assert result is not None
        assert result[1].effective_price_cents == 749900

    dispose_db()
