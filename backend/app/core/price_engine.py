from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.adapters.base import PriceQuote
from app.core.models import Listing, PriceSnapshot, Product, ProductPriceSnapshot


def save_price_snapshot(db: Session, listing: Listing, quote: PriceQuote) -> PriceSnapshot:
    snapshot = PriceSnapshot(
        listing_id=listing.id,
        captured_at=quote.captured_at,
        source=quote.source,
        page_price_cents=quote.page_price_cents,
        coupon_discount_cents=quote.coupon_discount_cents,
        estimated_price_cents=quote.estimated_price_cents,
        checkout_price_cents=quote.checkout_price_cents,
        effective_price_cents=quote.effective_price_cents,
        shipping_cents=quote.shipping_cents,
        coupon_breakdown=quote.coupon_breakdown or [],
        status=quote.status,
        error_message=quote.error,
    )
    db.add(snapshot)
    listing.last_checked_at = quote.captured_at
    db.commit()
    db.refresh(snapshot)
    return snapshot


def compute_lowest(
    quotes: list[tuple[Listing, PriceQuote]],
) -> tuple[Listing, PriceQuote, dict[str, str], dict[str, str]] | None:
    valid = [
        (listing, quote)
        for listing, quote in quotes
        if quote.status == "ok" and quote.effective_price_cents > 0
    ]
    if not valid:
        return None

    coverage: dict[str, str] = {}
    source_mix: dict[str, str] = {}
    for listing, quote in quotes:
        coverage[listing.platform] = quote.status
        if quote.status == "ok":
            source_mix[listing.platform] = quote.source

    lowest_listing, lowest_quote = min(valid, key=lambda item: item[1].effective_price_cents)
    return lowest_listing, lowest_quote, coverage, source_mix


def previous_low_cents(db: Session, product_id: int) -> int | None:
    return db.scalar(
        select(func.min(ProductPriceSnapshot.lowest_price_cents)).where(
            ProductPriceSnapshot.product_id == product_id
        )
    )


def is_new_low(candidate_cents: int, previous_cents: int | None) -> bool:
    if previous_cents is None:
        return False
    threshold = max(100, int(previous_cents * 0.001))
    return candidate_cents < previous_cents - threshold


def record_product_snapshot(
    db: Session,
    product: Product,
    quotes: list[tuple[Listing, PriceQuote]],
) -> tuple[ProductPriceSnapshot, bool, int | None]:
    lowest = compute_lowest(quotes)
    if lowest is None:
        raise ValueError("No valid price quotes")

    listing, quote, coverage, source_mix = lowest
    previous = previous_low_cents(db, product.id)
    new_low = is_new_low(quote.effective_price_cents, previous)

    snapshot = ProductPriceSnapshot(
        product_id=product.id,
        captured_at=quote.captured_at,
        lowest_price_cents=quote.effective_price_cents,
        lowest_platform=listing.platform,
        lowest_listing_id=listing.id,
        previous_low_cents=previous,
        is_new_low=new_low,
        coverage=coverage,
        source_mix=source_mix,
    )
    db.add(snapshot)
    db.commit()
    db.refresh(snapshot)
    return snapshot, new_low, previous


def latest_product_snapshot(db: Session, product_id: int) -> ProductPriceSnapshot | None:
    return db.scalar(
        select(ProductPriceSnapshot)
        .where(ProductPriceSnapshot.product_id == product_id)
        .order_by(ProductPriceSnapshot.captured_at.desc(), ProductPriceSnapshot.id.desc())
        .limit(1)
    )


def history_low_cents(db: Session, product_id: int) -> int | None:
    return db.scalar(
        select(func.min(ProductPriceSnapshot.lowest_price_cents)).where(
            ProductPriceSnapshot.product_id == product_id
        )
    )
