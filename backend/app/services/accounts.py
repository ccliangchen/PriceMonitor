from __future__ import annotations

import asyncio
import shutil
from contextlib import suppress

from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.registry import get_adapter
from app.config import Settings
from app.core.db import session_scope
from app.core.models import Account, utcnow
from app.services.browser import BrowserService

_login_tasks: dict[int, asyncio.Task[None]] = {}


def ensure_jd_account(db: Session, settings: Settings) -> Account:
    account = db.scalar(
        select(Account).where(Account.platform == "jd").order_by(Account.id)
    )
    if account is not None:
        return account

    account = Account(
        platform="jd",
        display_name="京东账号",
        profile_dir=str(settings.browser_profiles_dir / "jd_default"),
        status="needs_login",
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    return account


def start_login(account_id: int) -> bool:
    existing = _login_tasks.get(account_id)
    if existing is not None and not existing.done():
        return False

    task = asyncio.create_task(_run_login(account_id))
    _login_tasks[account_id] = task

    def cleanup(done: asyncio.Task[None]) -> None:
        if _login_tasks.get(account_id) is done:
            _login_tasks.pop(account_id, None)
        if not done.cancelled():
            with suppress(Exception):
                done.exception()

    task.add_done_callback(cleanup)
    return True


async def _run_login(account_id: int) -> None:
    with session_scope() as db:
        account = db.get(Account, account_id)
        if account is None:
            return
        account.status = "logging_in"
        db.commit()
        db.refresh(account)
        platform = account.platform

    adapter = get_adapter(platform)
    if adapter is None:
        _update_status(account_id, "error")
        return

    try:
        result = await adapter.login(account)
    except asyncio.CancelledError:
        _update_status(account_id, "needs_login")
        raise
    except Exception:
        logger.exception("JD login failed")
        _update_status(account_id, "needs_login")
        return
    finally:
        # A closed browser or an unexpected failure must never leave the
        # account stuck in "logging_in".
        _clear_logging_in(account_id)

    _update_status(
        account_id,
        "logged_in" if result.logged_in else "needs_login",
        last_login=result.logged_in,
    )


def _update_status(account_id: int, status: str, last_login: bool = False) -> None:
    with session_scope() as db:
        account = db.get(Account, account_id)
        if account is None:
            return
        account.status = status
        if last_login:
            account.last_login_at = utcnow()
        db.commit()


def _clear_logging_in(account_id: int) -> None:
    with session_scope() as db:
        account = db.get(Account, account_id)
        if account is not None and account.status == "logging_in":
            account.status = "needs_login"
            db.commit()


def reconcile_stale_logins(db: Session) -> None:
    stale = db.scalars(select(Account).where(Account.status == "logging_in")).all()
    if not stale:
        return
    changed = False
    for account in stale:
        task = _login_tasks.get(account.id)
        if task is None or task.done():
            account.status = "needs_login"
            changed = True
    if changed:
        db.commit()


async def logout_account(account_id: int, browser: BrowserService) -> None:
    task = _login_tasks.get(account_id)
    if task is not None and not task.done():
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    with session_scope() as db:
        account = db.get(Account, account_id)
        if account is None:
            return
        profile_dir = account.profile_dir

    await browser.close_context(profile_dir)
    shutil.rmtree(profile_dir, ignore_errors=True)

    with session_scope() as db:
        account = db.get(Account, account_id)
        if account is None:
            return
        account.status = "needs_login"
        account.last_login_at = None
        db.commit()
    logger.info("JD account {} logged out", account_id)


async def check_account(account_id: int, browser: BrowserService) -> str:
    with session_scope() as db:
        account = db.get(Account, account_id)
        if account is None:
            return "needs_login"
        platform = account.platform

    adapter = get_adapter(platform)
    if adapter is None:
        return "error"

    result = await adapter.check_login(account)
    status = "logged_in" if result.logged_in else "needs_login"
    _update_status(account_id, status, last_login=result.logged_in)
    return status
