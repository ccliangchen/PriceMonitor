from __future__ import annotations

import asyncio
import random

from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.base import PlatformAdapter, PriceQuote
from app.adapters.registry import get_adapter
from app.core.db import session_scope
from app.core.exceptions import (
    CaptchaRequired,
    LoginRequired,
    ParseError,
    RateLimited,
    ShopNotAllowed,
)
from app.core.models import Account, JobRun, Listing, PriceSnapshot, Product, utcnow
from app.core.platforms import platform_label
from app.core.price_engine import record_product_snapshot, save_price_snapshot
from app.core.settings_store import load_settings
from app.services.checkout import effective_quotes
from app.services.edge_bridge import edge_bridge
from app.services.notifications import send_new_low_notification

_poll_lock = asyncio.Lock()
MAX_CONSECUTIVE_FAILURES = 3


async def _fetch_listing_quote(
    listing: Listing, account: Account | None, adapter: PlatformAdapter
) -> PriceQuote:
    if listing.platform == "jd":
        return await edge_bridge.fetch(listing)
    if listing.platform != "taobao":
        return await adapter.fetch_page_price(listing, account)
    if account is None or account.status != "logged_in":
        return await edge_bridge.fetch(listing)

    try:
        direct_quote = await adapter.fetch_page_price(listing, account)
    except ShopNotAllowed:
        raise
    except Exception as direct_error:
        logger.warning(
            "Taobao listing {} direct capture failed ({}); starting selected browser if needed",
            listing.id,
            direct_error,
        )
        try:
            browser_quote = await edge_bridge.fetch(listing)
            if browser_quote.status != "ok":
                browser_quote.error = (
                    f"淘宝应用内浏览器访问受限：{direct_error}；"
                    f"所选浏览器扩展未读到完整商品页：{browser_quote.error or browser_quote.status}"
                )
            return browser_quote
        except ShopNotAllowed:
            raise
        except Exception as edge_error:
            raise RateLimited(
                f"淘宝直接抓取失败：{direct_error}；浏览器扩展备用抓取失败：{edge_error}"
            ) from edge_error

    if direct_quote.status == "ok" and direct_quote.confidence != "low":
        return direct_quote
    logger.warning(
        "Taobao listing {} direct capture returned {} confidence={} price={} page={}; trying selected browser",
        listing.id,
        direct_quote.status,
        direct_quote.confidence,
        direct_quote.effective_price_cents,
        direct_quote.page_price_cents,
    )
    try:
        browser_quote = await edge_bridge.fetch(listing)
        if browser_quote.status == "ok":
            return browser_quote
        if direct_quote.status == "ok":
            logger.warning(
                "Taobao listing {} selected browser returned {}; retaining direct low-confidence quote",
                listing.id,
                browser_quote.status,
            )
            direct_quote.error = (
                "淘宝直读价格尚未核实，浏览器扩展返回访问异常页；本轮未更新价格"
            )
            return direct_quote
        return browser_quote
    except ShopNotAllowed:
        raise
    except Exception as edge_error:
        if direct_quote.status == "ok":
            return direct_quote
        raise RateLimited(
            f"淘宝直接抓取失败：{direct_quote.error or direct_quote.status}；"
            f"浏览器扩展备用抓取失败：{edge_error}"
        ) from edge_error


async def poll_all() -> None:
    async with _poll_lock:
        with session_scope() as db:
            product_ids = list(
                db.scalars(
                    select(Listing.product_id)
                    .join(Product, Listing.product_id == Product.id)
                    .where(Listing.status == "active", Product.monitoring_enabled.is_(True))
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
        if product is None or not product.monitoring_enabled:
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
            db.refresh(product)
            if not product.monitoring_enabled:
                break

            label = platform_label(listing.platform)
            account = accounts.get(listing.platform)
            if listing.platform == "taobao" and listing.capture_mode != "primary":
                listing.capture_mode = "primary"
                db.commit()
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
                quote = await _fetch_listing_quote(listing, account, adapter)
                _hold_unconfirmed_jd_drop(db, listing, quote)
                save_price_snapshot(db, listing, quote)
                if quote.status == "ok" and quote.confidence == "high" and not listing.shop_verified:
                    listing.shop_verified = True
                job.status = "ok" if quote.status == "ok" else "failed"
                job.error_message = quote.error
                job.finished_at = utcnow()
                db.commit()
                if quote.status == "ok" and quote.confidence != "low":
                    quotes.append((listing, quote))
                elif quote.status == "ok":
                    job.status = "skipped"
                    job.error_message = quote.error or "低置信度价格，未参与比价"
                    db.commit()
                else:
                    await _maybe_pause_after_failures(db, listing, quote.error)
            except LoginRequired as exc:
                if listing.platform != "jd" and account is not None:
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
            except RateLimited as exc:
                _save_failure_snapshot(db, listing, "rate_limited", str(exc))
                job.status = "failed"
                job.error_message = str(exc)
                job.finished_at = utcnow()
                db.commit()
                logger.warning(
                    "{} rate limited while polling listing {}; retry on next poll",
                    label,
                    listing.id,
                )
                continue
            except CaptchaRequired as exc:
                if listing.platform != "taobao":
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
                    "{} captcha while polling listing {}; {}",
                    label,
                    listing.id,
                    "retry on next poll" if listing.platform == "taobao" else "paused without push",
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

        db.refresh(product)
        if not product.monitoring_enabled or not quotes:
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


def _hold_unconfirmed_jd_drop(db: Session, listing: Listing, quote: PriceQuote) -> None:
    """Wait for the next scheduled poll before trusting an extreme page drop."""
    if (
        listing.platform != "jd"
        or quote.source != "page"
        or quote.status != "ok"
        or quote.confidence == "low"
        or quote.effective_price_cents <= 0
    ):
        return
    recent = db.scalars(
        select(PriceSnapshot)
        .where(
            PriceSnapshot.listing_id == listing.id,
            PriceSnapshot.source == "page",
            PriceSnapshot.status == "ok",
            PriceSnapshot.effective_price_cents > 0,
        )
        .order_by(PriceSnapshot.captured_at.desc(), PriceSnapshot.id.desc())
        .limit(10)
    ).all()
    baseline = next((row for row in recent if row.confidence == "high"), None)
    if baseline is None or quote.effective_price_cents * 10 >= baseline.effective_price_cents * 6:
        return
    quote.confidence = "low"
    logger.warning(
        "JD listing {} page price {} is below 60% of prior high-confidence {}; "
        "not eligible for new-low notifications",
        listing.id,
        quote.effective_price_cents,
        baseline.effective_price_cents,
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
        if status in ("ok", "rate_limited"):
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
    if listing.platform == "taobao" and error and "访问异常/降级" in error:
        # A temporary platform response must not permanently disable polling.
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
