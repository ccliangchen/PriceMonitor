from __future__ import annotations

import asyncio
import json
import random
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

from loguru import logger

from app.adapters.base import PriceQuote
from app.core.exceptions import CaptchaRequired, LoginRequired, ParseError, RateLimited
from app.core.models import Listing
from app.services.capture_browser import capture_browser_launcher

PLATFORMS = frozenset({"jd", "taobao"})
BROWSERS = frozenset({"edge", "chrome", "firefox"})
JD_PC_GAP_SECONDS = (30.0, 60.0)
CONNECTED_TTL_SECONDS = 15.0


class JdVisitPacer:
    """Serialize all JD PC pages and retain the randomized gap across restarts."""

    def __init__(
        self,
        gap_seconds: tuple[float, float] = JD_PC_GAP_SECONDS,
        *,
        clock: Callable[[], float] = time.monotonic,
        wall_clock: Callable[[], float] = time.time,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        uniform: Callable[[float, float], float] | None = None,
    ) -> None:
        self.gap_seconds = gap_seconds
        self.clock = clock
        self.wall_clock = wall_clock
        self.sleep = sleep
        self.uniform = uniform or random.SystemRandom().uniform
        self.lock = asyncio.Lock()
        self.next_allowed = 0.0
        self.frequency_warning = False
        self.state_file: Path | None = None

    def configure(self, state_file: Path) -> None:
        self.state_file = state_file
        self.next_allowed = 0.0
        self.frequency_warning = False
        has_new_warning = False
        try:
            saved = json.loads(state_file.read_text(encoding="utf-8"))
            expiry = saved.get("next_allowed_at")
            if isinstance(expiry, (int, float)):
                self.next_allowed = self.clock() + max(0.0, expiry - self.wall_clock())
            if isinstance(saved.get("frequency_warning"), bool):
                self.frequency_warning = saved["frequency_warning"]
                has_new_warning = True
            # Old versions stored a blocking deadline. Carry its state forward
            # only as a warning; it must never prevent a user-requested visit.
            blocked_expiry = saved.get("blocked_until_at")
            if (not has_new_warning and isinstance(blocked_expiry, (int, float))
                    and blocked_expiry > self.wall_clock()):
                self.frequency_warning = True
        except (OSError, ValueError, TypeError, AttributeError):
            pass
    def _save(self) -> None:
        if self.state_file is None:
            return
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.state_file.with_suffix(self.state_file.suffix + ".tmp")
            temporary.write_text(
                json.dumps({
                    "next_allowed_at": self.wall_clock() + self.next_allowed - self.clock(),
                    "frequency_warning": self.frequency_warning,
                }),
                encoding="utf-8",
            )
            temporary.replace(self.state_file)
        except OSError:
            logger.warning("Could not save JD PC visit interval")

    async def run(self, visit: Callable[[], Awaitable[dict]]) -> dict:
        async with self.lock:
            delay = max(0.0, self.next_allowed - self.clock())
            if delay:
                logger.info("Waiting {:.1f}s before next JD PC page", delay)
                await self.sleep(delay)
            try:
                observation = await visit()
                final_url = str(observation.get("url") or "")
                if "pc-frequent" in final_url or "risk_handler" in final_url:
                    self.frequency_warning = True
                elif final_url:
                    self.frequency_warning = False
                return observation
            finally:
                self.next_allowed = self.clock() + self.uniform(*self.gap_seconds)
                self._save()


@dataclass
class PendingPage:
    platform: str
    url: str
    sku_id: str | None
    kind: str
    future: asyncio.Future[dict]
    claimed_event: asyncio.Event
    force_new_tab: bool = False
    bootstrap_token: str | None = None
    claimed_browser: str | None = None


class EdgeBridge:
    """One scheduled page request becomes one browser extension tab observation."""

    def __init__(self) -> None:
        self.queue: asyncio.Queue[str] = asyncio.Queue()
        self.pending: dict[str, PendingPage] = {}
        self.last_seen: dict[tuple[str, str], float] = {}
        self.protocol_versions: dict[str, int] = {}
        self.selected_browser = "edge"
        self.jd_pacer = JdVisitPacer()
        self.browser_launcher = capture_browser_launcher
        self.browser_start_lock = asyncio.Lock()
        self.browser_connect_timeout = 30.0
        self.browser_connect_poll = 0.5
        self.browser_claim_timeout = 12.0

    def set_browser(self, browser: str) -> None:
        if browser not in BROWSERS:
            raise ValueError("Unsupported capture browser")
        if browser == self.selected_browser:
            return
        self.selected_browser = browser
        for request_id, pending in self.pending.items():
            if pending.claimed_browser is not None and not pending.future.done():
                pending.claimed_browser = None
                self.queue.put_nowait(request_id)

    def connected(self, platform: str) -> bool:
        return (
            time.monotonic() - self.last_seen.get((self.selected_browser, platform), 0)
            <= CONNECTED_TTL_SECONDS
        )

    def connected_browsers(self) -> list[str]:
        now = time.monotonic()
        return [
            browser for browser in ("edge", "chrome", "firefox")
            if any(
                now - self.last_seen.get((browser, platform), 0) <= CONNECTED_TTL_SECONDS
                for platform in PLATFORMS
            )
        ]

    async def fetch(self, listing: Listing) -> PriceQuote:
        platform = listing.platform
        if platform not in PLATFORMS:
            raise ValueError("Unsupported Edge platform")
        if platform == "jd":
            sku = listing.platform_sku_id or listing.platform_item_id
            url = f"https://item.jd.com/{sku}.html"
        else:
            from app.adapters.taobao.adapter import _listing_target
            url = _listing_target(listing.url)
        observation = await self.observe(platform, url, listing.platform_sku_id)
        try:
            quote = self._quote_from_observation(listing, observation)
        except (CaptchaRequired, LoginRequired, ParseError, RateLimited):
            if not (platform == "taobao" and observation.get("reused_tab")):
                raise
            quote = None
        if platform == "taobao" and observation.get("reused_tab") and (
            quote is None or quote.status != "ok" or quote.confidence == "low"
        ):
            logger.info(
                "Taobao listing {} reused tab was unusable; opening a fresh visible tab",
                listing.id,
            )
            observation = await self.observe(
                platform, url, listing.platform_sku_id, force_new_tab=True
            )
            quote = self._quote_from_observation(listing, observation)
        return quote

    def _quote_from_observation(self, listing: Listing, observation: dict) -> PriceQuote:
        platform = listing.platform
        final_url = urlparse(observation["url"])
        reason = parse_qs(final_url.query).get("reason", [""])[0][:32]
        logger.info(
            "Edge {} listing {} observed host={}, path={}, reason={}, reused_tab={}, visibility={}",
            platform,
            listing.id,
            final_url.hostname or "",
            final_url.path,
            reason,
            observation.get("reused_tab", False),
            observation.get("visibility_state", "unknown"),
        )
        from app.adapters.registry import get_adapter

        adapter = get_adapter(platform)
        if platform == "jd":
            from app.adapters.jd.adapter import JdAdapter

            if not isinstance(adapter, JdAdapter):
                raise RuntimeError("JD adapter is unavailable")
            return adapter.quote_from_observation(
                listing,
                observation["url"],
                observation["title"],
                observation["body"],
                observation["price_texts"],
                observation["shop_texts"],
                observation["coupon_texts"],
                observation["html"],
                observation["primary_text"],
                observation["primary_price_texts"],
                require_primary=True,
            )

        from app.adapters.taobao.adapter import TaobaoAdapter

        if not isinstance(adapter, TaobaoAdapter):
            raise RuntimeError("Taobao adapter is unavailable")
        try:
            return adapter.quote_from_observation(
                listing,
                observation["url"],
                observation["title"],
                observation["body"],
                observation["price_texts"],
                observation["shop_texts"],
                observation["coupon_texts"],
                observation["html"],
                observation.get("title_texts", []),
            )
        except (CaptchaRequired, LoginRequired) as exc:
            # The browser profile is independent of the app's account.
            # Keep this listing scheduled for the next interval.
            raise RateLimited(f"浏览器扩展的淘宝页面受限：{exc}") from exc

    async def observe(
        self, platform: str, url: str, sku_id: str | None = None,
        kind: str = "product", force_new_tab: bool = False,
    ) -> dict:
        if platform not in PLATFORMS or kind != "product":
            raise ValueError("Unsupported browser observation")
        async def visit() -> dict:
            bootstrap_token = await self._ensure_browser_connected(platform, url)
            return await self._request_observation(
                platform, url, sku_id, kind, force_new_tab, bootstrap_token
            )
        if platform == "jd":
            return await self.jd_pacer.run(visit)
        return await visit()

    async def _ensure_browser_connected(self, platform: str, url: str) -> str | None:
        if self.connected(platform):
            return None
        async with self.browser_start_lock:
            if self.connected(platform):
                return None
            bootstrap_token = uuid4().hex
            try:
                await self.browser_launcher.launch(self.selected_browser, bootstrap_token)
            except (FileNotFoundError, OSError) as exc:
                raise RateLimited(str(exc)) from exc
            deadline = time.monotonic() + self.browser_connect_timeout
            while time.monotonic() < deadline:
                if self.connected(platform):
                    return bootstrap_token
                await asyncio.sleep(self.browser_connect_poll)
            raise RateLimited(
                f"已启动所选浏览器，但{platform}采价扩展未连接；请确认扩展已安装并启用"
            )

    async def _request_observation(
        self, platform: str, url: str, sku_id: str | None, kind: str,
        force_new_tab: bool = False, bootstrap_token: str | None = None,
    ) -> dict:
        loop = asyncio.get_running_loop()
        request_id = uuid4().hex
        future: asyncio.Future[dict] = loop.create_future()
        pending = PendingPage(
            platform=platform,
            url=url,
            sku_id=sku_id,
            kind=kind,
            future=future,
            claimed_event=asyncio.Event(),
            force_new_tab=force_new_tab,
            bootstrap_token=bootstrap_token,
        )
        self.pending[request_id] = pending
        await self.queue.put(request_id)
        try:
            try:
                await asyncio.wait_for(
                    pending.claimed_event.wait(), timeout=self.browser_claim_timeout
                )
            except TimeoutError:
                # A Chromium background process can keep the native connection
                # looking alive after its last window has closed, while its MV3
                # worker no longer claims work. Open the target window to wake it.
                if pending.claimed_browser is None and not future.done():
                    token = uuid4().hex
                    pending.bootstrap_token = token
                    try:
                        await self.browser_launcher.launch(self.selected_browser, token)
                    except (FileNotFoundError, OSError) as exc:
                        raise RateLimited(str(exc)) from exc
                    await self.queue.put(request_id)
                    logger.info(
                        "Started {} because {} request {} was not claimed",
                        self.selected_browser, platform, request_id[:8],
                    )
            observation = await asyncio.wait_for(future, timeout=150)
        except TimeoutError as exc:
            raise RateLimited("浏览器扩展未返回页面，请检查扩展连接或平台风控") from exc
        finally:
            self.pending.pop(request_id, None)
        if observation.get("error"):
            raise RateLimited(f"浏览器扩展未能读取页面：{observation['error']}")
        return observation

    def claim(
        self, capabilities: set[str] | None = None, browser: str = "edge",
        protocol_version: int = 1,
    ) -> dict | None:
        if browser not in BROWSERS:
            raise ValueError("Unsupported capture browser")
        supported = (capabilities or {"jd"}) & PLATFORMS
        now = time.monotonic()
        for platform in supported:
            self.last_seen[(browser, platform)] = now
        self.protocol_versions[browser] = protocol_version
        if browser != self.selected_browser:
            return None
        for _ in range(self.queue.qsize()):
            request_id = self.queue.get_nowait()
            pending = self.pending.get(request_id)
            if pending is None or pending.future.done():
                continue
            if pending.platform not in supported:
                self.queue.put_nowait(request_id)
                continue
            pending.claimed_browser = browser
            pending.claimed_event.set()
            logger.info("{} claimed {} {} request {}", browser, pending.platform, pending.kind, request_id[:8])
            return {
                "id": request_id,
                "platform": pending.platform,
                "url": pending.url,
                "sku_id": pending.sku_id,
                "kind": pending.kind,
                "force_new_tab": pending.force_new_tab,
                "isolated_window": True,
                "bootstrap_token": pending.bootstrap_token,
            }
        return None

    def submit(self, request_id: str, observation: dict, browser: str = "edge") -> bool:
        pending = self.pending.get(request_id)
        if (
            pending is None or pending.future.done()
            or pending.claimed_browser != browser
            or browser != self.selected_browser
        ):
            return False
        logger.info("{} returned {} {} request {}", browser, pending.platform, pending.kind, request_id[:8])
        pending.future.set_result(observation)
        return True


edge_bridge = EdgeBridge()
