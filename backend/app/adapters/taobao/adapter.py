from __future__ import annotations

import asyncio
import re
from contextlib import suppress
from datetime import UTC, datetime
from urllib.parse import urlparse

from loguru import logger
from playwright.async_api import Page

from app.adapters.base import ListingInfo, LoginStatus, PriceQuote
from app.adapters.taobao.parser import (
    GENERIC_TITLES,
    choose_title,
    extract_embedded_price_cents,
    extract_embedded_shop_name,
    extract_item_id,
    extract_sku_id,
    extract_ssr_sku_info,
    parse_checkout_payable_cents,
    parse_product_page,
)
from app.adapters.taobao.selectors import (
    COUPON_SELECTORS,
    PRICE_SELECTORS,
    SHOP_SELECTORS,
    TITLE_SELECTORS,
)
from app.core.exceptions import CaptchaRequired, LoginRequired, ParseError, ShopNotAllowed
from app.core.models import Account, Listing
from app.core.product_query import suggest_fields_from_title
from app.services.browser import BrowserService

TAOBAO_LOGIN_URL = "https://login.taobao.com/member/login.jhtml"
TAOBAO_HOME_URL = "https://www.taobao.com/"
LOGIN_TIMEOUT_SECONDS = 300


def has_login_cookies(cookies: list[dict]) -> bool:
    names = {cookie.get("name") for cookie in cookies}
    # ``unb`` alone can be issued to anonymous visitors; a real login also
    # sets the nickname/login markers.
    return "unb" in names and bool({"tracknick", "cookie17", "login"} & names)


class TaobaoAdapter:
    platform = "taobao"

    def __init__(self, browser: BrowserService) -> None:
        self.browser = browser

    async def resolve_listing(self, url: str, account: Account | None = None) -> ListingInfo:
        if account is None:
            raise LoginRequired("请先登录淘宝")
        target = normalize_url(url)
        async with self.browser.session(account.profile_dir, headless=True) as page:
            await self._goto(page, target)
            final_url = page.url
            title, body, price_texts, shop_texts, coupon_texts = (
                await self._read_page_settled(page)
            )
            self._assert_not_blocked(final_url, title, body)
            if title in GENERIC_TITLES:
                if "请登录" in body or "扫码登录" in body:
                    raise LoginRequired("淘宝登录态失效，请重新登录")
                raise ParseError(
                    "商品页面没有加载完整（标题为空），请稍后重试；"
                    "如果反复出现，请到账号管理检查淘宝登录"
                )
            html = await page.content()
            embedded_shop = extract_embedded_shop_name(html)
            if embedded_shop:
                shop_texts = [embedded_shop, *shop_texts]
            parsed = parse_product_page(
                url=final_url,
                title=title,
                body_text=body + "\n" + "\n".join(coupon_texts),
                price_texts=price_texts,
                shop_texts=shop_texts,
                embedded_price_cents=extract_embedded_price_cents(html),
            )
            if parsed.status == "login_required":
                raise LoginRequired(parsed.error or "淘宝登录态失效，请重新登录")
            if parsed.status == "captcha":
                raise CaptchaRequired(parsed.error or "淘宝触发验证")
            item_id = extract_item_id(final_url) or extract_item_id(target)
            if item_id is None:
                raise ParseError("请粘贴淘宝/天猫商品详情页链接，而不是搜索或店铺首页")
            canonical_url = _listing_target(final_url)
            product_title = parsed.title or title or f"淘宝商品 {item_id}"
            detected_specs = parse_specs(product_title)
            detected_specs.update(
                {
                    key: value
                    for key, value in suggest_fields_from_title(product_title).items()
                    if value
                }
            )
            return ListingInfo(
                platform=self.platform,
                url=canonical_url,
                title=product_title,
                shop_name=parsed.shop_name,
                shop_type=parsed.shop_type,
                platform_item_id=item_id,
                platform_sku_id=extract_sku_id(final_url),
                detected_specs=detected_specs,
                evidence=parsed.evidence,
            )

    async def fetch_page_price(self, listing: Listing, account: Account) -> PriceQuote:
        target = _listing_target(listing.url)
        async with self.browser.session(account.profile_dir, headless=True) as page:
            await self._goto(page, target)
            final_url = page.url
            title, body, price_texts, shop_texts, coupon_texts = (
                await self._read_page_settled(page)
            )
            self._assert_not_blocked(final_url, title, body)
            if len(body.strip()) < 40:
                raise CaptchaRequired("淘宝页面没有加载出内容，可能被限流，请稍后重试")
            html = await page.content()
            embedded_shop = extract_embedded_shop_name(html)
            if embedded_shop:
                shop_texts = [embedded_shop, *shop_texts]
            parsed = parse_product_page(
                url=final_url,
                title=title,
                body_text=body + "\n" + "\n".join(coupon_texts),
                price_texts=price_texts,
                shop_texts=shop_texts,
                embedded_price_cents=extract_embedded_price_cents(html),
            )

            if parsed.status == "login_required":
                raise LoginRequired(parsed.error or "淘宝登录态失效，请重新登录")
            if parsed.status == "captcha":
                raise CaptchaRequired(parsed.error or "淘宝触发验证")

            if parsed.shop_type == "other":
                raise ShopNotAllowed("当前商品不是淘宝/天猫官方旗舰店")
            if parsed.shop_type not in ("unknown", listing.shop_type):
                raise ShopNotAllowed("店铺类型发生变化，请重新确认")
            self._assert_shop_unchanged(listing, parsed.shop_name)

            ssr_info = extract_ssr_sku_info(html, listing.platform_sku_id)
            ssr_price = ssr_info.price_cents if ssr_info is not None else None
            if ssr_info is not None and (
                any(word in ssr_info.stock_text for word in ("无货", "售罄", "缺货", "下架"))
                or (ssr_info.quantity is not None and ssr_info.quantity <= 0)
            ):
                raise ParseError("该淘宝 SKU 当前无货，暂不记录价格")
            if (
                ssr_info is not None
                and ssr_info.sub_price_cents is not None
                and ssr_info.sub_price_title not in ("优惠前", "原价", "划线价")
                and "访问异常" not in (parsed.error or "")
            ):
                # SSR subPrice is the per-SKU final price after coupons/subsidy.
                parsed.page_price_cents = (
                    ssr_info.price_cents or parsed.page_price_cents
                )
                parsed.estimated_price_cents = ssr_info.sub_price_cents
                if (
                    parsed.page_price_cents is not None
                    and parsed.page_price_cents > ssr_info.sub_price_cents
                ):
                    parsed.coupon_discount_cents = (
                        parsed.page_price_cents - ssr_info.sub_price_cents
                    )
                parsed.confidence = "high"
                parsed.status = "ok"
                parsed.error = None
            if parsed.confidence == "high" and (
                not listing.platform_sku_id or ssr_info is None
            ):
                # Without a confirmed SKU id and SSR SKU entry we cannot
                # guarantee the price belongs to the monitored specification.
                parsed.confidence = "low"
            if (
                parsed.status == "parse_error"
                and ssr_price is not None
                and "访问异常" not in (parsed.error or "")
            ):
                parsed.page_price_cents = parsed.page_price_cents or ssr_price
                parsed.estimated_price_cents = ssr_price
                parsed.confidence = "low"
                parsed.status = "ok"
                parsed.error = None
            elif parsed.status == "ok" and parsed.estimated_price_cents is None:
                if ssr_price is not None:
                    parsed.estimated_price_cents = ssr_price
                    parsed.page_price_cents = parsed.page_price_cents or ssr_price
                    parsed.confidence = parsed.confidence or "low"

            effective = parsed.estimated_price_cents or parsed.page_price_cents or 0
            status = parsed.status
            if status == "ok" and effective <= 0:
                status = "parse_error"

            return PriceQuote(
                platform=self.platform,
                listing_id=listing.id,
                source="page",
                effective_price_cents=effective,
                confidence=parsed.confidence,
                captured_at=datetime.now(UTC),
                page_price_cents=parsed.page_price_cents,
                coupon_discount_cents=parsed.coupon_discount_cents,
                estimated_price_cents=parsed.estimated_price_cents,
                coupon_breakdown=parsed.coupon_breakdown,
                status=status,
                error=parsed.error,
            )

    async def login(self, account: Account) -> LoginStatus:
        async with self.browser.session(account.profile_dir, headless=False) as page:
            await page.goto(TAOBAO_LOGIN_URL, wait_until="domcontentloaded", timeout=60_000)
            await page.wait_for_timeout(1500)
            deadline = asyncio.get_running_loop().time() + LOGIN_TIMEOUT_SECONDS
            while asyncio.get_running_loop().time() < deadline:
                if page.is_closed():
                    raise LoginRequired("登录窗口已关闭")
                cookies = await page.context.cookies()
                if has_login_cookies(cookies):
                    logger.info("Taobao login detected")
                    return LoginStatus(
                        logged_in=True,
                        message="淘宝登录成功",
                        display_name=_cookie_value(cookies, "tracknick"),
                    )
                await page.wait_for_timeout(2000)
        raise LoginRequired("登录超时，请重新发起登录")

    async def check_login(self, account: Account) -> LoginStatus:
        async with self.browser.session(account.profile_dir, headless=True) as page:
            try:
                await page.goto(TAOBAO_HOME_URL, wait_until="domcontentloaded", timeout=60_000)
                await page.wait_for_timeout(1000)
            except Exception as exc:
                logger.warning("Taobao login check navigation failed: {}", exc)
            cookies = await page.context.cookies()
            logged_in = has_login_cookies(cookies)
            return LoginStatus(
                logged_in=logged_in,
                message="淘宝已登录" if logged_in else "淘宝未登录",
                display_name=_cookie_value(cookies, "tracknick") if logged_in else None,
            )

    async def open_verification(self, listing: Listing, account: Account) -> LoginStatus:
        target = _listing_target(listing.url)
        async with self.browser.session(account.profile_dir, headless=False) as page:
            await page.goto(target, wait_until="domcontentloaded", timeout=60_000)
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
                    "验证码拦截" in title
                    or "_____tmd_____" in page.url
                    or "滑动" in body
                    or "验证" in title
                    or len(body.strip()) < 40
                )
                loaded = "立即购买" in body or "加入购物车" in body
                if not blocked and (loaded or "¥" in body or "￥" in body):
                    return LoginStatus(logged_in=True, message="淘宝验证已完成")
                await page.wait_for_timeout(2_000)
        raise CaptchaRequired("等待验证超时，请重试")

    async def fetch_checkout_price(
        self,
        listing: Listing,
        account: Account,
        headless: bool = False,
    ) -> PriceQuote:
        """Read the payable amount on the Taobao confirmation page.

        Manual calls use a visible browser so the user can solve a slider or
        finish the navigation. Automatic calls run headless and give up
        quietly. This method never clicks "提交订单" or a payment button.
        """
        wait_seconds = 30 if headless else 180
        target = _listing_target(listing.url)
        async with self.browser.session(account.profile_dir, headless=headless) as page:
            await self._goto(page, target)
            await _click_exact_text(page, "立即购买")

            deadline = asyncio.get_running_loop().time() + wait_seconds
            while asyncio.get_running_loop().time() < deadline:
                if page.is_closed():
                    raise ParseError("结算窗口已关闭")
                try:
                    title = await page.title()
                    body = await page.locator("body").inner_text(timeout=10_000)
                except Exception:
                    title = ""
                    body = ""
                if "login.taobao.com" in page.url or "login.tmall.com" in page.url:
                    raise LoginRequired("淘宝登录态失效，请重新登录")
                if "_____tmd_____" in page.url or "验证码拦截" in title:
                    await page.wait_for_timeout(2_000)
                    continue

                on_confirm_page = any(
                    phrase in body for phrase in ("提交订单", "确认订单", "实付款")
                )
                if on_confirm_page:
                    payable = parse_checkout_payable_cents(body)
                    if payable is None:
                        with suppress(Exception):
                            payable = parse_checkout_payable_cents(await page.content())
                    if payable is not None:
                        return PriceQuote(
                            platform=self.platform,
                            listing_id=listing.id,
                            source="checkout",
                            effective_price_cents=payable,
                            confidence="high",
                            captured_at=datetime.now(UTC),
                            checkout_price_cents=payable,
                            status="ok",
                        )
                await page.wait_for_timeout(2_000)
        raise ParseError(
            "没有在淘宝确认订单页读到实付款；可能需要人工处理验证或选择地址"
        )

    async def _goto(self, page: Page, url: str) -> None:
        await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        with suppress(Exception):
            await page.wait_for_function(
                "() => /[¥￥]\\s*[0-9]/.test(document.body.innerText)"
                " || location.href.includes('login.')"
                " || location.href.includes('_____tmd_____')",
                timeout=8_000,
            )
        await page.wait_for_timeout(1_000)

    async def _read_page(
        self, page: Page
    ) -> tuple[str, str, list[str], list[str], list[str], list[str]]:
        title = await page.title()
        try:
            body = await page.locator("body").inner_text(timeout=10_000)
        except Exception:
            body = ""
        title_texts = await _collect_texts(page, TITLE_SELECTORS)
        price_texts = await _collect_texts(page, PRICE_SELECTORS)
        shop_texts = await _collect_texts(page, SHOP_SELECTORS)
        coupon_texts = await _collect_texts(page, COUPON_SELECTORS)
        return title, body, price_texts, shop_texts, coupon_texts, title_texts

    async def _read_page_settled(
        self, page: Page
    ) -> tuple[str, str, list[str], list[str], list[str]]:
        runtime = ""
        body = ""
        price_texts: list[str] = []
        shop_texts: list[str] = []
        coupon_texts: list[str] = []
        for attempt in range(4):
            runtime, body, price_texts, shop_texts, coupon_texts, title_texts = (
                await self._read_page(page)
            )
            title = choose_title(runtime, title_texts)
            if title and title not in GENERIC_TITLES and len(title) >= 8:
                return title, body, price_texts, shop_texts, coupon_texts
            if attempt < 3:
                await page.wait_for_timeout(1_500)
        return (
            choose_title(runtime, title_texts),
            body,
            price_texts,
            shop_texts,
            coupon_texts,
        )

    @staticmethod
    def _assert_not_blocked(url: str, title: str, body: str) -> None:
        if "_____tmd_____" in url or "/punish" in url or "验证码拦截" in title:
            raise CaptchaRequired("淘宝触发验证，请打开验证页完成滑块")
        if "login.taobao.com" in url or "login.tmall.com" in url:
            raise LoginRequired("淘宝登录态失效，请重新登录")
        if any(phrase in body for phrase in ("请按住滑块", "拖动滑块", "滑动验证", "安全验证")):
            raise CaptchaRequired("淘宝触发滑块验证，请打开验证页完成")
        if any(phrase in title or phrase in body for phrase in ("访问频繁", "系统繁忙", "稍后再试")):
            raise CaptchaRequired("淘宝访问频繁，请稍后再试（不要连续刷新）")

    @staticmethod
    def _assert_shop_unchanged(listing: Listing, current_shop_name: str) -> None:
        previous = re.sub(r"\s+", "", listing.shop_name or "")
        current = re.sub(r"\s+", "", current_shop_name or "")
        if not previous or not current or current == "未知店铺":
            return
        if previous == current or previous in current or current in previous:
            return
        raise ShopNotAllowed("店铺名称发生变化，已暂停监控，请重新确认官方店铺")


FORBIDDEN_CLICK_TEXTS = (
    "提交订单",
    "立即支付",
    "确认支付",
    "去支付",
    "付款",
)


async def _click_exact_text(page: Page, text: str) -> bool:
    if any(word in text for word in FORBIDDEN_CLICK_TEXTS):
        raise ValueError(f"拒绝点击下单/支付按钮：{text}")
    try:
        locator = page.get_by_text(text, exact=True)
        count = await locator.count()
        for index in range(count - 1, -1, -1):
            item = locator.nth(index)
            with suppress(Exception):
                if await item.is_visible():
                    await item.click(timeout=3_000)
                    return True
    except Exception:
        pass
    try:
        return bool(
            await page.evaluate(
                """(text) => {
                    const all = [...document.querySelectorAll('div,button,a,span')];
                    const matches = all.filter(
                        (el) => (el.innerText || '').trim() === text
                            && el.offsetParent !== null
                    );
                    if (!matches.length) return false;
                    matches[matches.length - 1].click();
                    return true;
                }""",
                text,
            )
        )
    except Exception:
        return False


async def _collect_texts(page: Page, selectors: list[str]) -> list[str]:
    texts: list[str] = []
    for selector in selectors:
        try:
            locator = page.locator(selector)
            count = await locator.count()
            for index in range(min(count, 20)):
                text = (await locator.nth(index).inner_text(timeout=1000)).strip()
                if text and len(text) <= 200:
                    texts.append(text)
        except Exception:
            continue
    return list(dict.fromkeys(texts))


def normalize_url(url: str) -> str:
    value = url.strip()
    if not value:
        raise ParseError("请输入淘宝/天猫商品链接")
    if not value.startswith(("http://", "https://")):
        value = f"https://{value}"
    parsed = urlparse(value)
    host = parsed.netloc.lower()
    allowed = (
        host == "taobao.com"
        or host.endswith(".taobao.com")
        or host == "tmall.com"
        or host.endswith(".tmall.com")
        or host == "tb.cn"
        or host.endswith(".tb.cn")
    )
    if not allowed:
        raise ParseError("只支持淘宝/天猫商品链接")

    item_id = extract_item_id(value)
    if item_id is not None:
        # Drop promotion/tracking parameters (fpChannel, mi_id, ...). They can
        # lead to a stripped-down page without the real title/price.
        if "tmall.com" in host:
            canonical = f"https://detail.tmall.com/item.htm?id={item_id}"
        else:
            canonical = f"https://item.taobao.com/item.htm?id={item_id}"
        sku_id = extract_sku_id(value)
        if sku_id is not None:
            canonical = f"{canonical}&skuId={sku_id}"
        return canonical

    return value


def _cookie_value(cookies: list[dict], name: str) -> str | None:
    for cookie in cookies:
        if cookie.get("name") == name:
            value = str(cookie.get("value") or "").strip()
            if value:
                return value
    return None


def _listing_target(url: str) -> str:
    try:
        return normalize_url(url)
    except ParseError:
        return url


def parse_specs(title: str) -> dict[str, str]:
    specs: dict[str, str] = {}
    match = re.search(
        r"(\d{1,3})\s*(?:GB|G)\s*(?:\+| )\s*(\d{1,4})\s*(?:GB|G)",
        title,
        re.IGNORECASE,
    )
    if match:
        specs["ram_gb"] = match.group(1)
        specs["storage_gb"] = match.group(2)
    return specs
