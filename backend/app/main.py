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

from app import __version__
from app.api.router import api_router
from app.config import Settings
from app.core.db import init_db


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
        logger.info("SQLite ready at {}", settings.db_path)
        yield
        logger.info("Backend shutting down")

    app = FastAPI(
        title="PriceMonitor Backend",
        version=__version__,
        docs_url=None,
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.settings = settings
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
