from __future__ import annotations

import asyncio
from contextlib import suppress

from loguru import logger
from sqlalchemy import select

from app.adapters.registry import get_adapter
from app.core.db import session_scope
from app.core.models import Account, Listing
from app.services.browser import BrowserService

_verify_tasks: dict[int, asyncio.Task[None]] = {}


def start_verification(listing_id: int, browser: BrowserService) -> bool:
    existing = _verify_tasks.get(listing_id)
    if existing is not None and not existing.done():
        return False

    task = asyncio.create_task(_run_verification(listing_id, browser))
    _verify_tasks[listing_id] = task

    def cleanup(done: asyncio.Task[None]) -> None:
        if _verify_tasks.get(listing_id) is done:
            _verify_tasks.pop(listing_id, None)
        if not done.cancelled():
            with suppress(Exception):
                done.exception()

    task.add_done_callback(cleanup)
    return True


async def _run_verification(listing_id: int, browser: BrowserService) -> None:
    with session_scope() as db:
        listing = db.get(Listing, listing_id)
        if listing is None:
            return
        listing.status = "verifying"
        db.commit()
        db.refresh(listing)
        platform = listing.platform

    with session_scope() as db:
        account = db.scalar(
            select(Account).where(Account.platform == platform).order_by(Account.id)
        )
        if account is None:
            logger.warning("No account for platform {}", platform)

    adapter = get_adapter(platform)
    status = "paused"
    try:
        if adapter is None:
            raise RuntimeError(f"No adapter for {platform}")
        await adapter.open_verification(listing, account)
        status = "active"
    except asyncio.CancelledError:
        status = "paused"
        raise
    except Exception:
        logger.exception("JD verification failed")
        status = "paused"
    finally:
        with session_scope() as db:
            row = db.get(Listing, listing_id)
            if row is not None:
                row.status = status
                db.commit()
