from __future__ import annotations

import asyncio
import random

from loguru import logger
from sqlalchemy import select

from app.adapters.base import PriceQuote
from app.adapters.registry import get_adapter
from app.core.db import session_scope
from app.core.exceptions import (
    CaptchaRequired,
    LoginRequired,
    ParseError,
    ShopNotAllowed,
)
from app.core.models import Account, JobRun, Listing, Product, utcnow
from app.core.price_engine import record_product_snapshot, save_price_snapshot
from app.services.notifications import send_new_low_notification

_poll_lock = asyncio.Lock()


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


async def poll_product(product_id: int) -> None:
    async with _poll_lock:
        await _poll_product(product_id)


async def _poll_product(product_id: int) -> None:
    with session_scope() as db:
        product = db.get(Product, product_id)
        if product is None:
            return
        listings = [item for item in product.listings if item.status == "active"]
        if not listings:
            return

        account = db.scalar(
            select(Account).where(Account.platform == "jd").order_by(Account.id)
        )
        if account is None or account.status != "logged_in":
            logger.warning("Skipping product {}: JD account is not logged in", product_id)
            return

        quotes = []
        for index, listing in enumerate(listings):
            if index > 0:
                delay = random.uniform(20, 40)
                logger.info("Waiting {:.1f}s before polling next listing", delay)
                await asyncio.sleep(delay)
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
                quote = await adapter.fetch_page_price(listing, account)
                save_price_snapshot(db, listing, quote)
                job.status = "ok" if quote.status == "ok" else "failed"
                job.error_message = quote.error
                job.finished_at = utcnow()
                db.commit()
                quotes.append((listing, quote))
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
                logger.warning("JD login required while polling listing {}", listing.id)
                break
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
                logger.warning("JD captcha while polling listing {}", listing.id)
                break
            except ShopNotAllowed as exc:
                listing.status = "paused"
                job.status = "failed"
                job.error_message = str(exc)
                job.finished_at = utcnow()
                db.commit()
                logger.warning("Listing {} paused: {}", listing.id, exc)
                continue
            except ParseError as exc:
                job.status = "failed"
                job.error_message = str(exc)
                job.finished_at = utcnow()
                db.commit()
                logger.warning("Parse error for listing {}: {}", listing.id, exc)
                continue
            except Exception as exc:
                job.status = "failed"
                job.error_message = str(exc)
                job.finished_at = utcnow()
                db.commit()
                logger.exception("Unexpected error polling listing {}", listing.id)
                continue

        if not quotes:
            return

        snapshot, new_low, _previous = record_product_snapshot(db, product, quotes)
        if not new_low:
            return

        valid = [
            (listing, quote)
            for listing, quote in quotes
            if quote.status == "ok" and quote.effective_price_cents > 0
        ]
        if not valid:
            return
        lowest_listing, lowest_quote = min(
            valid, key=lambda item: item[1].effective_price_cents
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
