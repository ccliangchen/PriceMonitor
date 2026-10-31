from __future__ import annotations

import asyncio
import re
from contextlib import suppress
from datetime import UTC, datetime
from urllib.parse import urlparse

from loguru import logger
from playwright.async_api import Page

from app.adapters.base import ListingInfo, LoginStatus, PriceQuote
from app.adapters.jd.parser import (
    SkuVariant,
    extract_embedded_price_cents,
    extract_sku,
    parse_product_page,
    parse_sku_variants,
)
from app.adapters.jd.selectors import (
    COUPON_SELECTORS,
    PRICE_SELECTORS,
    SHOP_SELECTORS,
)
from app.core.exceptions import CaptchaRequired, LoginRequired, ParseError, ShopNotAllowed
from app.core.models import Account, Listing
from app.services.browser import BrowserService

JD_LOGIN_URL = "https://passport.jd.com/new/login.aspx"
JD_HOME_URL = "https://www.jd.com/"
LOGIN_TIMEOUT_SECONDS = 300

LOGIN_COOKIE_PAIRS = (
    {"pt_key", "pt_pin"},
    {"thor", "pin"},
    {"thor", "unick"},
)


def has_login_cookies(cookie_names: set[str]) -> bool:
    return any(pair.issubset(cookie_names) for pair in LOGIN_COOKIE_PAIRS)


class JdAdapter:
    platform = "jd"

    def __init__(self, browser: BrowserService) -> None:
        self.browser = browser

    async def resolve_listing(self, url: str, account: Account | None = None) -> ListingInfo:
        if account is None:
            raise LoginRequired("请先登录京东")
        target = prefer_mobile_url(normalize_url(url))
        async with self.browser.session(account.profile_dir, headless=True) as page:
            await self._goto(page, target)
            final_url = page.url
            title, body, price_texts, shop_texts, _coupon_texts = await self._read_page(page)
            self._assert_not_blocked(final_url, title, body)
            html = await page.content()
            parsed = parse_product_page(
                url=final_url,
                title=title,
                body_text=body,
                price_texts=price_texts,
                shop_texts=shop_texts,
                embedded_price_cents=extract_embedded_price_cents(html),
            )
            sku = extract_sku(final_url)
            if sku is None:
                raise ParseError("请粘贴京东商品详情页链接，而不是搜索/列表页")
            return ListingInfo(
                platform=self.platform,
                url=final_url,
                title=parsed.title or title or f"京东商品 {sku}",
                shop_name=parsed.shop_name,
                shop_type=parsed.shop_type,
                platform_item_id=sku,
                platform_sku_id=None,
                detected_specs=parse_specs(parsed.title),
                evidence=parsed.evidence,
            )

    async def fetch_page_price(self, listing: Listing, account: Account) -> PriceQuote:
        async with self.browser.session(account.profile_dir, headless=True) as page:
            await self._goto(page, prefer_mobile_url(listing.url))
            final_url = page.url
            title, body, price_texts, shop_texts, coupon_texts = await self._read_page(page)
            self._assert_not_blocked(final_url, title, body)
            if len(body.strip()) < 40:
                raise CaptchaRequired("京东页面没有加载出内容，可能被限流，请稍后重试")
            html = await page.content()
            parsed = parse_product_page(
                url=final_url,
                title=title,
                body_text=body + "\n" + "\n".join(coupon_texts),
                price_texts=price_texts,
                shop_texts=shop_texts,
                embedded_price_cents=extract_embedded_price_cents(html),
            )

            if parsed.shop_type == "other":
                raise ShopNotAllowed("当前商品不是官方旗舰店/官方自营")
            if parsed.shop_type not in ("unknown", listing.shop_type):
                raise ShopNotAllowed("店铺类型发生变化，请重新确认")

            effective = parsed.estimated_price_cents or parsed.page_price_cents or 0
            status = parsed.status
            if status == "ok" and effective <= 0:
                status = "parse_error"

            return PriceQuote(
                platform=self.platform,
                listing_id=listing.id,
                source="page",
                effective_price_cents=effective,
                captured_at=datetime.now(UTC),
                page_price_cents=parsed.page_price_cents,
                coupon_discount_cents=parsed.coupon_discount_cents,
                estimated_price_cents=parsed.estimated_price_cents,
                coupon_breakdown=parsed.coupon_breakdown,
                status=status,
                error=parsed.error,
            )

    async def get_sku_variants(
        self,
        url: str,
        account: Account,
    ) -> tuple[str, list[SkuVariant]]:
        async with self.browser.session(account.profile_dir, headless=True) as page:
            await self._goto(page, prefer_mobile_url(normalize_url(url)))
            final_url = page.url
            title, body, _price_texts, _shop_texts, _coupon_texts = await self._read_page(page)
            self._assert_not_blocked(final_url, title, body)
            if len(body.strip()) < 40:
                raise CaptchaRequired("京东页面没有加载出内容，可能被限流，请稍后重试")
            html = await page.content()
            return title, parse_sku_variants(html)

    async def login(self, account: Account) -> LoginStatus:
        async with self.browser.session(account.profile_dir, headless=False) as page:
            await page.goto(JD_LOGIN_URL, wait_until="domcontentloaded", timeout=60_000)
            await page.wait_for_timeout(1500)
            deadline = asyncio.get_running_loop().time() + LOGIN_TIMEOUT_SECONDS
            while asyncio.get_running_loop().time() < deadline:
                if page.is_closed():
                    raise LoginRequired("登录窗口已关闭")
                cookies = await page.context.cookies()
                names = {cookie["name"] for cookie in cookies}
                if has_login_cookies(names):
                    logger.info("JD login detected")
                    return LoginStatus(logged_in=True, message="京东登录成功")
                await page.wait_for_timeout(2000)
        raise LoginRequired("登录超时，请重新发起登录")

    async def open_verification(self, listing: Listing, account: Account) -> LoginStatus:
        """Open a headed JD page and wait for the user to clear a verification."""
        async with self.browser.session(account.profile_dir, headless=False) as page:
            await page.goto(
                prefer_mobile_url(listing.url),
                wait_until="domcontentloaded",
                timeout=60_000,
            )
            await page.wait_for_timeout(2_000)
            deadline = asyncio.get_running_loop().time() + 300
            while asyncio.get_running_loop().time() < deadline:
                if page.is_closed():
                    raise CaptchaRequired("验证窗口已关闭")
                try:
                    title = await page.title()
                    body = await page.locator("body").inner_text(timeout=10_000)
                except Exception:
                    title = ""
                    body = ""
                blocked = (
                    "京东验证" in title
                    or "验证一下" in body
                    or "访问频繁" in body
                    or "pc-frequent-pro" in page.url
                    or len(body.strip()) < 40
                )
                if not blocked and ("¥" in body or "￥" in body):
                    return LoginStatus(logged_in=True, message="京东验证已完成")
                await page.wait_for_timeout(2_000)
        raise CaptchaRequired("等待验证超时，请重试")

    async def check_login(self, account: Account) -> LoginStatus:
        async with self.browser.session(account.profile_dir, headless=True) as page:
            try:
                await page.goto(JD_HOME_URL, wait_until="domcontentloaded", timeout=60_000)
                await page.wait_for_timeout(1000)
            except Exception as exc:
                logger.warning("JD login check navigation failed: {}", exc)
            cookies = await page.context.cookies()
            names = {cookie["name"] for cookie in cookies}
            logged_in = has_login_cookies(names)
            return LoginStatus(
                logged_in=logged_in,
                message="京东已登录" if logged_in else "京东未登录",
            )

    async def _goto(self, page: Page, url: str) -> None:
        await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        # Mobile JD pages render the price asynchronously. Wait for a visible
        # currency amount instead of relying on a fixed sleep.
        with suppress(Exception):
            await page.wait_for_function(
                "() => /[¥￥]\\s*[0-9]/.test(document.body.innerText)",
                timeout=8_000,
            )
        await page.wait_for_timeout(1_000)

    async def _read_page(
        self, page: Page
    ) -> tuple[str, str, list[str], list[str], list[str]]:
        title = await page.title()
        try:
            body = await page.locator("body").inner_text(timeout=10_000)
        except Exception:
            body = ""
        price_texts = await _collect_texts(page, PRICE_SELECTORS)
        shop_texts = await _collect_texts(page, SHOP_SELECTORS)
        coupon_texts = await _collect_texts(page, COUPON_SELECTORS)
        return title, body, price_texts, shop_texts, coupon_texts

    @staticmethod
    def _assert_not_blocked(url: str, title: str, body: str) -> None:
        if (
            "pc-frequent-pro" in url
            or "PC频控页" in title
            or "暂时无法展示该商品的信息" in body
        ):
            raise CaptchaRequired("京东访问频繁（PC频控），请稍后重试或改用移动版链接")
        rate_limit_phrases = (
            "访问频繁",
            "系统繁忙",
            "网络繁忙",
            "操作频繁",
            "请求异常",
            "稍后再试",
            "活动太火爆",
            "排队进场",
        )
        if any(phrase in title or phrase in body for phrase in rate_limit_phrases):
            raise CaptchaRequired("京东访问频繁，请稍后重试（不要连续刷新）")
        if "risk_handler" in url or "京东验证" in title or "验证一下" in body:
            raise CaptchaRequired("京东触发验证，请稍后重试或手动登录")
        if "passport.jd.com" in url or "请登录" in body:
            raise LoginRequired("京东登录态失效，请重新登录")


async def _collect_texts(page: Page, selectors: list[str]) -> list[str]:
    texts: list[str] = []
    for selector in selectors:
        try:
            locator = page.locator(selector)
            count = await locator.count()
            for index in range(min(count, 30)):
                text = (await locator.nth(index).inner_text(timeout=1000)).strip()
                if text:
                    texts.append(text)
        except Exception:
            continue
    return list(dict.fromkeys(texts))


def normalize_url(url: str) -> str:
    value = url.strip()
    if not value:
        raise ParseError("请输入京东商品链接")
    if not value.startswith(("http://", "https://")):
        value = f"https://{value}"
    parsed = urlparse(value)
    host = parsed.netloc.lower()
    allowed = (
        host == "jd.com"
        or host.endswith(".jd.com")
        or host == "3.cn"
        or host.endswith(".3.cn")
    )
    if not allowed:
        raise ParseError("只支持京东商品链接")
    return value


def prefer_mobile_url(url: str) -> str:
    """Desktop item pages are frequently PC-rate-limited; use the mobile item page."""
    sku = extract_sku(url)
    if sku is None:
        return url
    parsed = urlparse(url)
    if parsed.netloc.lower() == "item.jd.com":
        return f"https://item.m.jd.com/product/{sku}.html"
    return url


def parse_specs(title: str) -> dict[str, str]:
    specs: dict[str, str] = {}
    match = re.search(r"(\d{1,3})\s*GB\s*(?:\+| )\s*(\d{1,4})\s*GB", title, re.IGNORECASE)
    if match:
        specs["ram_gb"] = match.group(1)
        specs["storage_gb"] = match.group(2)
    return specs
