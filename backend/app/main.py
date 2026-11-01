from __future__ import annotations

import argparse
import os
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from loguru import logger
from sqlalchemy import update

from app import __version__
from app.adapters.jd.adapter import JdAdapter
from app.adapters.registry import register
from app.adapters.taobao.adapter import TaobaoAdapter
from app.api.router import api_router
from app.config import Settings
from app.core.db import init_db, session_scope
from app.core.models import JobRun, utcnow
from app.core.scheduler import create_scheduler
from app.core.settings_store import load_settings
from app.services.browser import BrowserService


def configure_logging(settings: Settings) -> None:
    settings.logs_dir.mkdir(parents=True, exist_ok=True)
    logger.remove()
    if sys.stderr is not None:
        logger.add(sys.stderr, level=settings.log_level.upper(), enqueue=False)
    logger.add(
        settings.logs_dir / "backend.log",
        level=settings.log_level.upper(),
        rotation="10 MB",
        retention=5,
        encoding="utf-8",
        enqueue=True,
    )


def create_app(settings: Settings) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        settings.logs_dir.mkdir(parents=True, exist_ok=True)
        settings.browser_profiles_dir.mkdir(parents=True, exist_ok=True)
        settings.exports_dir.mkdir(parents=True, exist_ok=True)
        init_db(settings.data_dir)
        with session_scope() as db:
            db.execute(
                update(JobRun)
                .where(JobRun.status == "running")
                .values(
                    status="failed",
                    finished_at=utcnow(),
                    error_message="应用重启，任务中断",
                )
            )
            db.commit()
        logger.info("SQLite ready at {}", settings.db_path)

        if settings.enable_scheduler:
            with session_scope() as db:
                interval = int(load_settings(db)["poll_interval_minutes"])
            scheduler = create_scheduler(interval)
            scheduler.start()
            _app.state.scheduler = scheduler
            logger.info("Price poll scheduler started ({} minutes)", interval)

        yield

        scheduler = getattr(_app.state, "scheduler", None)
        if scheduler is not None:
            scheduler.shutdown(wait=False)
        await _app.state.browser.stop()
        logger.info("Backend shutting down")

    browser = BrowserService()
    register(JdAdapter(browser))
    register(TaobaoAdapter(browser))

    app = FastAPI(
        title="PriceMonitor Backend",
        version=__version__,
        docs_url=None,
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.browser = browser
    app.state.scheduler = None
    app.state.started_at = time.monotonic()
    app.include_router(api_router)
    return app


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="PriceMonitor backend sidecar")
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--data-dir", type=Path, default=None)
    parser.add_argument("--log-level", type=str, default=None)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    token = os.environ.get("PRICE_MONITOR_TOKEN", "").strip()
    if not token:
        print("PRICE_MONITOR_TOKEN is required", file=sys.stderr)
        return 2

    base = Settings()
    settings = base.model_copy(
        update={
            "port": args.port if args.port is not None else base.port,
            "data_dir": args.data_dir if args.data_dir is not None else base.data_dir,
            "token": token,
            "log_level": args.log_level or base.log_level,
        }
    )
    configure_logging(settings)
    app = create_app(settings)
    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=settings.port,
        log_level=settings.log_level.lower(),
        access_log=False,
    )
    server = uvicorn.Server(config)
    app.state.server = server
    logger.info("PriceMonitor backend {} listening on 127.0.0.1:{}", __version__, settings.port)
    server.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
