from __future__ import annotations

import asyncio
import random
import time

from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.base import PriceQuote
from app.adapters.registry import get_adapter
from app.core.db import session_scope
from app.core.exceptions import (
    CaptchaRequired,
    LoginRequired,
    ParseError,
    ShopNotAllowed,
)
from app.core.models import Account, JobRun, Listing, PriceSnapshot, Product, utcnow
from app.core.platforms import platform_label
from app.core.price_engine import record_product_snapshot, save_price_snapshot
from app.core.settings_store import load_settings
from app.services.checkout import effective_quotes
from app.services.notifications import send_new_low_notification

_poll_lock = asyncio.Lock()
MAX_CONSECUTIVE_FAILURES = 3
# Deep JD desktop probes can hit PC frequency control. Scheduled polling tries
# one at most every six hours per listing; manual refresh always tries.
_DEEP_PRICE_INTERVAL_SECONDS = 6 * 3600
_last_deep_attempt: dict[int, float] = {}


def _should_try_deep(listing_id: int) -> bool:
    last = _last_deep_attempt.get(listing_id, 0.0)
    return time.monotonic() - last >= _DEEP_PRICE_INTERVAL_SECONDS


async def poll_all() -> None:
    async with _poll_lock:
        with session_scope() as db:
            product_ids = list(
                db.scalars(
                    select(Listing.product_id)
                    .where(Listing.status == "active")
                    .distinct()
                ).all()
            )
        for index, product_id in enumerate(product_ids):
            if index > 0:
                delay = random.uniform(20, 40)
                logger.info("Waiting {:.1f}s before polling next product", delay)
                await asyncio.sleep(delay)
            try:
                await _poll_product(product_id)
            except Exception:
                logger.exception("Polling product {} failed", product_id)


async def poll_product(product_id: int, deep: bool = False) -> None:
    async with _poll_lock:
        await _poll_product(product_id, deep=deep)


async def _poll_product(product_id: int, deep: bool = False) -> None:
    with session_scope() as db:
        product = db.get(Product, product_id)
        if product is None:
            return
        listings = [item for item in product.listings if item.status == "active"]
        if not listings:
            return

        accounts = {
            account.platform: account
            for account in db.scalars(select(Account).order_by(Account.id)).all()
        }

        quotes: list[tuple[Listing, PriceQuote]] = []
        for index, listing in enumerate(listings):
            if index > 0:
                delay = random.uniform(20, 40)
                logger.info("Waiting {:.1f}s before polling next listing", delay)
                await asyncio.sleep(delay)

            label = platform_label(listing.platform)
            account = accounts.get(listing.platform)
            if account is None or account.status != "logged_in":
                job = JobRun(
                    platform=listing.platform,
                    listing_id=listing.id,
                    job_type="page_price",
                    status="skipped",
                    error_message=f"{label}账号未登录",
                    finished_at=utcnow(),
                )
                db.add(job)
                db.commit()
                logger.warning(
                    "Skipping listing {}: {} account is not logged in",
                    listing.id,
                    label,
                )
                continue

            job = JobRun(
                platform=listing.platform,
                listing_id=listing.id,
                job_type="page_price",
                status="running",
            )
            db.add(job)
            db.commit()

            adapter = get_adapter(listing.platform)
            if adapter is None:
                job.status = "failed"
                job.error_message = f"No adapter for {listing.platform}"
                job.finished_at = utcnow()
                db.commit()
                continue

            try:
                # Manual refresh may additionally try JD's desktop page to
                # read coupon/subsidy labels absent from the mobile page.
                # Scheduled polling also tries a deep probe at most every
                # six hours; the adapter falls back to mobile on PC risk.
                deep_fetch = getattr(adapter, "fetch_page_price_deep", None)
                use_deep = deep or (
                    deep_fetch is not None and _should_try_deep(listing.id)
                )
                if use_deep and deep_fetch is not None:
                    _last_deep_attempt[listing.id] = time.monotonic()
                    quote = await deep_fetch(listing, account)
                else:
                    quote = await adapter.fetch_page_price(listing, account)
                save_price_snapshot(db, listing, quote)
                job.status = "ok" if quote.status == "ok" else "failed"
                job.error_message = quote.error
                job.finished_at = utcnow()
                db.commit()
                if quote.status == "ok" and quote.confidence != "low":
                    quotes.append((listing, quote))
                elif quote.status == "ok":
                    job.status = "skipped"
                    job.error_message = "低置信度价格，未参与比价"
                    db.commit()
                else:
                    await _maybe_pause_after_failures(db, listing, quote.error)
            except LoginRequired as exc:
                account.status = "needs_login"
                save_price_snapshot(
                    db,
                    listing,
                    PriceQuote(
                        platform=listing.platform,
                        listing_id=listing.id,
                        source="page",
                        effective_price_cents=0,
                        status="login_required",
                        error=str(exc),
                    ),
                )
                job.status = "failed"
                job.error_message = str(exc)
                job.finished_at = utcnow()
                db.commit()
                # Do not spend the limited WeChat push quota on login/pause
                # events. The account and job status are visible in the app.
                logger.warning("{} login required while polling listing {}", label, listing.id)
                continue
            except CaptchaRequired as exc:
                listing.status = "paused"
                save_price_snapshot(
                    db,
                    listing,
                    PriceQuote(
                        platform=listing.platform,
                        listing_id=listing.id,
                        source="page",
                        effective_price_cents=0,
                        status="captcha",
                        error=str(exc),
                    ),
                )
                job.status = "failed"
                job.error_message = str(exc)
                job.finished_at = utcnow()
                db.commit()
                logger.warning(
                    "{} captcha while polling listing {}; paused without push",
                    label,
                    listing.id,
                )
                continue
            except ShopNotAllowed as exc:
                listing.status = "paused"
                job.status = "failed"
                job.error_message = str(exc)
                job.finished_at = utcnow()
                db.commit()
                logger.warning("Listing {} paused without push: {}", listing.id, exc)
                continue
            except ParseError as exc:
                job.status = "failed"
                job.error_message = str(exc)
                job.finished_at = utcnow()
                db.commit()
                _save_failure_snapshot(db, listing, "parse_error", str(exc))
                logger.warning("Parse error for listing {}: {}", listing.id, exc)
                await _maybe_pause_after_failures(db, listing, str(exc))
                continue
            except Exception as exc:
                job.status = "failed"
                job.error_message = str(exc)
                job.finished_at = utcnow()
                db.commit()
                _save_failure_snapshot(db, listing, "error", str(exc))
                logger.exception("Unexpected error polling listing {}", listing.id)
                await _maybe_pause_after_failures(db, listing, str(exc))
                continue

        if not quotes:
            return

        # Fresh checkout prices are authoritative; otherwise use fresh page
        # estimates. This prevents a later page poll from overwriting a
        # recently calibrated checkout price.
        checkout_hours = int(load_settings(db)["checkout_interval_hours"])
        effective = effective_quotes(
            db,
            product,
            checkout_fresh_seconds=checkout_hours * 3600,
        )
        if not effective:
            return

        snapshot, new_low, _previous = record_product_snapshot(db, product, effective)
        if not new_low:
            return

        lowest_listing, lowest_quote = min(
            effective, key=lambda item: item[1].effective_price_cents
        )
        try:
            await send_new_low_notification(
                db,
                product,
                lowest_listing,
                lowest_quote,
                snapshot,
            )
        except Exception:
            logger.exception("Failed to send new-low notification")


def _save_failure_snapshot(
    db: Session,
    listing: Listing,
    status: str,
    error: str | None,
) -> None:
    save_price_snapshot(
        db,
        listing,
        PriceQuote(
            platform=listing.platform,
            listing_id=listing.id,
            source="page",
            effective_price_cents=0,
            status=status,  # type: ignore[arg-type]
            error=error,
        ),
    )


def _consecutive_failures(db: Session, listing_id: int) -> int:
    statuses = db.scalars(
        select(PriceSnapshot.status)
        .where(PriceSnapshot.listing_id == listing_id)
        .order_by(PriceSnapshot.captured_at.desc(), PriceSnapshot.id.desc())
        .limit(10)
    ).all()
    count = 0
    for status in statuses:
        if status == "ok":
            break
        count += 1
    return count


async def _maybe_pause_after_failures(
    db: Session,
    listing: Listing,
    error: str | None,
) -> None:
    if listing.status != "active":
        return
    failures = _consecutive_failures(db, listing.id)
    if failures < MAX_CONSECUTIVE_FAILURES:
        return
    listing.status = "paused"
    db.commit()
    # Pause/failure alerts stay in the app logs. WeChat quota is reserved for
    # genuine all-platform historical lows.
    logger.warning(
        "Listing {} paused after {} failures without push: {}",
        listing.id,
        failures,
        error or "未知错误",
    )
