from __future__ import annotations

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from loguru import logger

POLL_JOB_ID = "poll_all"


def _jitter_seconds(minutes: int) -> int:
    return max(5, min(180, int(minutes * 60 * 0.1)))


def create_scheduler(interval_minutes: int) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="Asia/Shanghai")
    _add_poll_job(scheduler, interval_minutes)
    return scheduler


def _add_poll_job(scheduler: AsyncIOScheduler, interval_minutes: int) -> None:
    scheduler.add_job(
        _poll_job,
        IntervalTrigger(minutes=interval_minutes),
        id=POLL_JOB_ID,
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=300,
        jitter=_jitter_seconds(interval_minutes),
    )


def reschedule_job(scheduler: AsyncIOScheduler, interval_minutes: int) -> None:
    _add_poll_job(scheduler, interval_minutes)


async def _poll_job() -> None:
    from app.services.monitor import poll_all

    try:
        await poll_all()
    except Exception:
        logger.exception("Scheduled price poll failed")
