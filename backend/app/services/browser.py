from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from playwright.async_api import BrowserContext, Page, Playwright, async_playwright

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/140.0.0.0 Safari/537.36 Edg/140.0.0.0"
)


class BrowserService:
    def __init__(self) -> None:
        self._playwright: Playwright | None = None
        self._contexts: dict[str, BrowserContext] = {}
        self._headless: dict[str, bool] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    async def start(self) -> None:
        if self._playwright is None:
            self._playwright = await async_playwright().start()

    async def stop(self) -> None:
        for profile_dir in list(self._contexts):
            await self.close_context(profile_dir)
        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None

    def _lock(self, profile_dir: str) -> asyncio.Lock:
        if profile_dir not in self._locks:
            self._locks[profile_dir] = asyncio.Lock()
        return self._locks[profile_dir]

    async def _open_context(self, profile_dir: str, headless: bool) -> BrowserContext:
        await self.start()
        if self._playwright is None:
            raise RuntimeError("Playwright failed to start")

        existing = self._contexts.get(profile_dir)
        if existing is not None and self._headless.get(profile_dir) == headless:
            return existing
        if existing is not None:
            await self.close_context(profile_dir)

        context = await self._playwright.chromium.launch_persistent_context(
            user_data_dir=profile_dir,
            channel="msedge",
            headless=headless,
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
            viewport={"width": 1366, "height": 768},
            user_agent=USER_AGENT,
            args=["--no-first-run", "--no-default-browser-check"],
            accept_downloads=False,
        )
        context.set_default_timeout(30_000)
        context.set_default_navigation_timeout(60_000)
        self._contexts[profile_dir] = context
        self._headless[profile_dir] = headless
        return context

    async def close_context(self, profile_dir: str) -> None:
        context = self._contexts.pop(profile_dir, None)
        self._headless.pop(profile_dir, None)
        if context is not None:
            with suppress(Exception):
                await context.close()

    @asynccontextmanager
    async def session(self, profile_dir: str, headless: bool = True) -> AsyncIterator[Page]:
        lock = self._lock(profile_dir)
        async with lock:
            context = await self._open_context(profile_dir, headless)
            page = await context.new_page()
            try:
                yield page
            finally:
                with suppress(Exception):
                    await page.close()
                await self.close_context(profile_dir)
