from __future__ import annotations

import asyncio
import time
from contextlib import suppress
from datetime import UTC, datetime, timedelta

from loguru import logger
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.adapters.base import PriceQuote
from app.adapters.registry import get_adapter
from app.core.db import session_scope
from app.core.exceptions import LoginRequired, ParseError
from app.core.models import (
    Account,
    JobRun,
    Listing,
    PriceSnapshot,
    Product,
    ProductPriceSnapshot,
    utcnow,
)
from app.core.price_engine import (
    is_new_low,
    plausible_page_price_clause,
    record_product_snapshot,
    save_price_snapshot,
)
from app.core.settings_store import load_settings
from app.services.notifications import send_new_low_notification

CHECKOUT_FRESH_SECONDS = 6 * 3600
PAGE_FRESH_SECONDS = 2 * 3600
_CHECKOUT_COOLDOWN_SECONDS = 600

_checkout_tasks: dict[int, asyncio.Task[None]] = {}
_active_checkouts: set[int] = set()
_last_checkout: dict[int, float] = {}


def checkout_cooldown_remaining(listing_id: int) -> int:
    last = _last_checkout.get(listing_id)
    if last is None:
        return 0
    remaining = _CHECKOUT_COOLDOWN_SECONDS - int(time.monotonic() - last)
    return max(0, remaining)


def start_checkout_calibration(listing_id: int) -> bool:
    existing = _checkout_tasks.get(listing_id)
    if existing is not None and not existing.done():
        return False
    if listing_id in _active_checkouts:
        return False
    if checkout_cooldown_remaining(listing_id) > 0:
        return False

    task = asyncio.create_task(_run_checkout_calibration(listing_id))
    _checkout_tasks[listing_id] = task
    _active_checkouts.add(listing_id)

    def cleanup(done: asyncio.Task[None]) -> None:
        if _checkout_tasks.get(listing_id) is done:
            _checkout_tasks.pop(listing_id, None)
        _active_checkouts.discard(listing_id)
        if not done.cancelled():
            with suppress(Exception):
                done.exception()

    task.add_done_callback(cleanup)
    return True


async def _run_checkout_calibration(
    listing_id: int,
    *,
    headless: bool = False,
) -> None:
    with session_scope() as db:
        listing = db.get(Listing, listing_id)
        if listing is None:
            return
        account = db.scalar(
            select(Account)
            .where(Account.platform == listing.platform)
            .order_by(Account.id)
        )
        if account is None or account.status != "logged_in":
            raise LoginRequired("账号未登录，无法校准结算价")
        product_id = listing.product_id
        job = JobRun(
            platform=listing.platform,
            listing_id=listing.id,
            job_type="checkout",
            status="running",
        )
        db.add(job)
        db.commit()
        db.refresh(job)

    adapter = get_adapter(listing.platform)
    try:
        if adapter is None:
            raise ParseError(f"没有 {listing.platform} 适配器")
        quote = await adapter.fetch_checkout_price(
            listing,
            account,
            headless=headless,
        )
        if quote.status != "ok" or quote.effective_price_cents <= 0:
            raise ParseError(quote.error or "没有读到结算应付金额")

        with session_scope() as db:
            row = db.get(Listing, listing_id)
            if row is None:
                return
            previous_checkout_low = _checkout_low(db, product_id)
            latest_page = _latest_ok_snapshot(db, listing_id, "page", 7 * 24 * 3600)
            if latest_page is not None:
                quote.page_price_cents = quote.page_price_cents or latest_page.page_price_cents
                quote.estimated_price_cents = (
                    quote.estimated_price_cents or latest_page.estimated_price_cents
                )
                quote.coupon_discount_cents = (
                    quote.coupon_discount_cents or latest_page.coupon_discount_cents
                )
                quote.coupon_breakdown = (
                    quote.coupon_breakdown or latest_page.coupon_breakdown or []
                )
                quote.shipping_cents = quote.shipping_cents or latest_page.shipping_cents
            save_price_snapshot(db, row, quote)
            if previous_checkout_low is not None and is_new_low(
                quote.effective_price_cents,
                previous_checkout_low,
            ):
                product = db.get(Product, product_id)
                if product is not None:
                    transient = ProductPriceSnapshot(
                        product_id=product_id,
                        lowest_price_cents=quote.effective_price_cents,
                        lowest_platform=row.platform,
                        lowest_listing_id=row.id,
                        previous_low_cents=previous_checkout_low,
                        is_new_low=True,
                        coverage={row.platform: "ok"},
                        source_mix={row.platform: "checkout"},
                    )
                    await send_new_low_notification(
                        db,
                        product,
                        row,
                        quote,
                        transient,
                    )
            await _refresh_product_snapshot(db, product_id)
            job_row = db.get(JobRun, job.id)
            if job_row is not None:
                job_row.status = "ok"
                job_row.finished_at = utcnow()
                db.commit()
        logger.info(
            "Checkout calibration for listing {}: {} cents",
            listing_id,
            quote.effective_price_cents,
        )
        _last_checkout[listing_id] = time.monotonic()
    except asyncio.CancelledError:
        _finish_job(job.id, "failed", "任务已取消")
        raise
    except LoginRequired as exc:
        logger.warning("Checkout calibration requires login for listing {}", listing_id)
        _mark_account_needs_login(listing.platform)
        _finish_job(job.id, "failed", str(exc))
        if not headless:
            _last_checkout[listing_id] = time.monotonic()
        raise
    except Exception as exc:
        if isinstance(exc, ParseError):
            logger.warning(
                "Checkout calibration failed for listing {}: {}",
                listing_id,
                exc,
            )
        else:
            logger.exception("Checkout calibration failed for listing {}", listing_id)
        _finish_job(job.id, "failed", str(exc))
        if not headless:
            _last_checkout[listing_id] = time.monotonic()
        raise


def _finish_job(job_id: int, status: str, error: str | None) -> None:
    with session_scope() as db:
        job = db.get(JobRun, job_id)
        if job is not None:
            job.status = status
            job.error_message = error
            job.finished_at = utcnow()
            db.commit()


def _checkout_low(db: Session, product_id: int) -> int | None:
    return db.scalar(
        select(func.min(PriceSnapshot.effective_price_cents))
        .join(Listing, PriceSnapshot.listing_id == Listing.id)
        .where(
            Listing.product_id == product_id,
            PriceSnapshot.source == "checkout",
            PriceSnapshot.status == "ok",
            PriceSnapshot.effective_price_cents > 0,
        )
    )


def _latest_ok_snapshot(
    db: Session,
    listing_id: int,
    source: str,
    fresh_seconds: int,
) -> PriceSnapshot | None:
    since = datetime.now(UTC) - timedelta(seconds=fresh_seconds)
    return db.scalar(
        select(PriceSnapshot)
        .where(
            PriceSnapshot.listing_id == listing_id,
            PriceSnapshot.source == source,
            PriceSnapshot.status == "ok",
            PriceSnapshot.captured_at >= since,
            PriceSnapshot.effective_price_cents > 0,
            plausible_page_price_clause(),
            or_(
                PriceSnapshot.confidence.is_(None),
                PriceSnapshot.confidence != "low",
            ),
        )
        .order_by(PriceSnapshot.captured_at.desc(), PriceSnapshot.id.desc())
        .limit(1)
    )


def effective_quotes(
    db: Session,
    product: Product,
    *,
    checkout_fresh_seconds: int = CHECKOUT_FRESH_SECONDS,
) -> list[tuple[Listing, PriceQuote]]:
    """Page price is the primary quote; checkout is only a fallback."""
    result: list[tuple[Listing, PriceQuote]] = []
    for listing in product.listings:
        if listing.status != "active":
            continue
        snapshot = _latest_ok_snapshot(db, listing.id, "page", PAGE_FRESH_SECONDS)
        if snapshot is None:
            snapshot = _latest_ok_snapshot(
                db, listing.id, "checkout", checkout_fresh_seconds
            )
        if snapshot is None:
            continue
        result.append(
            (
                listing,
                PriceQuote(
                    platform=listing.platform,
                    listing_id=listing.id,
                    source=snapshot.source,  # type: ignore[arg-type]
                    effective_price_cents=snapshot.effective_price_cents,
                    confidence=snapshot.confidence,  # type: ignore[arg-type]
                    captured_at=datetime.now(UTC),
                    page_price_cents=snapshot.page_price_cents,
                    coupon_discount_cents=snapshot.coupon_discount_cents,
                    estimated_price_cents=snapshot.estimated_price_cents,
                    checkout_price_cents=snapshot.checkout_price_cents,
                    shipping_cents=snapshot.shipping_cents,
                    coupon_breakdown=snapshot.coupon_breakdown or [],
                    status="ok",
                ),
            )
        )
    return result


async def _refresh_product_snapshot(db: Session, product_id: int) -> None:
    product = db.get(Product, product_id)
    if product is None:
        return
    checkout_hours = int(load_settings(db)["checkout_interval_hours"])
    quotes = effective_quotes(
        db,
        product,
        checkout_fresh_seconds=checkout_hours * 3600,
    )
    if not quotes:
        return
    snapshot, new_low, _previous = record_product_snapshot(db, product, quotes)
    if not new_low:
        return
    lowest_listing, lowest_quote = min(
        quotes, key=lambda item: item[1].effective_price_cents
    )
    await send_new_low_notification(
        db,
        product,
        lowest_listing,
        lowest_quote,
        snapshot,
    )


def _mark_account_needs_login(platform: str) -> None:
    with session_scope() as db:
        account = db.scalar(
            select(Account).where(Account.platform == platform).order_by(Account.id)
        )
        if account is not None:
            account.status = "needs_login"
            db.commit()
