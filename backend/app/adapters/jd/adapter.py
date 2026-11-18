from __future__ import annotations

import asyncio
import re
from contextlib import suppress
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlparse

from loguru import logger
from playwright.async_api import Page, Response

from app.adapters.base import ListingInfo, LoginStatus, PriceQuote
from app.adapters.jd.parser import (
    ANY_PRICE_RE,
    FINAL_PRICE_LABEL_RE,
    SkuVariant,
    extract_embedded_price_cents,
    extract_embedded_promotion_price_cents,
    extract_sku,
    parse_checkout_payable_cents,
    parse_product_page,
    parse_sku_variants,
)
from app.adapters.jd.selectors import (
    COUPON_SELECTORS,
    PRICE_SELECTORS,
    SHOP_SELECTORS,
)
from app.core.exceptions import (
    CaptchaRequired,
    LoginRequired,
    ParseError,
    RateLimited,
)
from app.core.models import Account, Listing
from app.core.product_query import suggest_fields_from_title
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


def _cookie_value(cookies: list[dict], name: str) -> str | None:
    for cookie in cookies:
        if cookie.get("name") == name:
            value = str(cookie.get("value") or "").strip()
            if value:
                return value
    return None


class JdAdapter:
    platform = "jd"

    def __init__(self, browser: BrowserService) -> None:
        self.browser = browser

    async def resolve_listing(self, url: str, account: Account | None = None) -> ListingInfo:
        if account is None:
            raise LoginRequired("请先登录京东")
        target = prefer_mobile_url(normalize_url(url))
        async with self.browser.resident_session(account.profile_dir) as page:
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
            product_title = clean_title(parsed.title or title or f"京东商品 {sku}")
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
                url=final_url,
                title=product_title,
                shop_name=parsed.shop_name,
                shop_type=parsed.shop_type,
                platform_item_id=sku,
                platform_sku_id=None,
                detected_specs=detected_specs,
                evidence=parsed.evidence,
            )

    async def fetch_page_price(self, listing: Listing, account: Account) -> PriceQuote:
        sku = extract_sku(listing.url) or listing.platform_item_id
        if not sku or not sku.isdigit():
            raise ParseError("京东商品缺少有效 SKU")
        return await self._fetch_page_quote(listing, account, f"https://item.jd.com/{sku}.html")

    async def _fetch_page_quote(
        self,
        listing: Listing,
        account: Account,
        target_url: str,
    ) -> PriceQuote:
        async with self.browser.resident_session(account.profile_dir) as page:
            response = await self._goto(page, target_url)
            final_url = page.url
            final = urlparse(final_url)
            reason = parse_qs(final.query).get("reason", [""])[0][:32]
            logger.info(
                "JD PC listing {} navigation: status={}, host={}, path={}, reason={}",
                listing.id,
                response.status if response is not None else "none",
                final.hostname or "",
                final.path,
                reason,
            )
            if response is not None and response.status in (403, 429):
                raise RateLimited("京东 PC 商品页拒绝访问，本轮未采价；下轮自动重试")
            title, body, price_texts, shop_texts, coupon_texts = await self._read_page(page)
            html = await page.content()
            return self.quote_from_observation(
                listing, final_url, title, body, price_texts,
                shop_texts, coupon_texts, html,
            )

    def quote_from_observation(
        self,
        listing: Listing,
        final_url: str,
        title: str,
        body: str,
        price_texts: list[str],
        shop_texts: list[str],
        coupon_texts: list[str],
        html: str,
        primary_text: str = "",
        primary_price_texts: list[str] | None = None,
        require_primary: bool = False,
    ) -> PriceQuote:
        """Parse a JD PC page observed by either browser channel."""
        self._assert_not_blocked(final_url, title, body)
        expected_sku = extract_sku(listing.url) or listing.platform_item_id
        if extract_sku(final_url) != expected_sku:
            raise ParseError("京东商品页 SKU 与监控商品不一致")
        if len(body.strip()) < 40:
            raise RateLimited("京东 PC 商品页未加载出内容，本轮未采价；下轮自动重试")
        previous_shop = re.sub(r"\s+", "", listing.shop_name or "")
        title_section = (
            _title_anchored_product_section(body, listing.title or title)
            if require_primary else ""
        )
        anchored_body = (
            _title_anchored_price_context(title_section)
            if require_primary else ""
        )
        matching_shops = [
            text
            for text in shop_texts
            if previous_shop and previous_shop in re.sub(r"\s+", "", text)
        ]
        seller_texts = matching_shops[:1] or shop_texts[:1]
        if not seller_texts and title_section:
            normalized_section = re.sub(r"\s+", "", title_section)
            if previous_shop and previous_shop in normalized_section:
                seller_texts = [listing.shop_name]
            else:
                section_shops = re.findall(
                    r"[A-Za-z0-9\u4e00-\u9fff]{2,32}"
                    r"(?:京东自营旗舰店|官方旗舰店|专营店|专卖店)",
                    title_section,
                )
                if section_shops:
                    seller_texts = [section_shops[0]]
                elif (
                    listing.shop_verified
                    and listing.shop_type == "jd_official_self"
                    and "京东自营" in title_section[:1200]
                ):
                    seller_texts = [listing.shop_name]
                elif listing.shop_verified and anchored_body:
                    # A JD item URL identifies the same SKU as the verified
                    # listing. Current layouts omit the seller selector, so
                    # retain that verified seller when the product title and
                    # nearby price both match the monitored item.
                    seller_texts = [listing.shop_name]
        price_body = anchored_body or (primary_text if require_primary and primary_text else body)
        logger.info(
            "JD listing {} price context: title_anchor={}, primary_region={}",
            listing.id,
            bool(anchored_body),
            bool(primary_text),
        )
        parsed = parse_product_page(
            url=final_url,
            title=title,
            body_text=price_body if require_primary else body + "\n" + "\n".join(coupon_texts),
            price_texts=([] if anchored_body else (primary_price_texts or [])) if require_primary else price_texts,
            shop_texts=seller_texts,
            embedded_price_cents=extract_embedded_price_cents(html),
        )
        logger.info(
            "JD listing {} seller: stored_type={}, observed_type={}, observed_name={}, candidates={}, matched={}",
            listing.id,
            listing.shop_type,
            parsed.shop_type,
            parsed.shop_name[:80],
            len(shop_texts),
            bool(matching_shops),
        )

        if parsed.shop_name and parsed.shop_name != "未知店铺":
            listing.shop_name = parsed.shop_name
            listing.shop_type = parsed.shop_type
        if parsed.confidence == "high" and extract_sku(listing.url) is None:
            parsed.confidence = "low"

        promo_price = None if require_primary else extract_embedded_promotion_price_cents(html)
        if (
            promo_price is not None
            and parsed.status == "ok"
            and (
                parsed.confidence == "low"
                or parsed.estimated_price_cents is None
                or promo_price < parsed.estimated_price_cents
            )
        ):
            parsed.page_price_cents = parsed.page_price_cents or promo_price
            parsed.estimated_price_cents = promo_price
            if parsed.page_price_cents is not None and parsed.page_price_cents > promo_price:
                parsed.coupon_discount_cents = parsed.page_price_cents - promo_price
            parsed.confidence = "high"
        explicit_final_price = bool(FINAL_PRICE_LABEL_RE.search(price_body))
        rejected_final_price = bool(
            require_primary
            and anchored_body
            and parsed.status == "ok"
            and parsed.page_price_cents
            and parsed.estimated_price_cents
            and parsed.estimated_price_cents * 4 < parsed.page_price_cents
        )
        if rejected_final_price:
            # The first amount beside the monitored title is the main item
            # price. A much smaller labelled amount later in the section can
            # belong to a recommendation or another promotion. Keep the
            # observed main price, without stacking any nearby coupons.
            logger.warning(
                "JD listing {} discarded implausible final label {} beside main price {}",
                listing.id,
                parsed.estimated_price_cents,
                parsed.page_price_cents,
            )
            parsed.estimated_price_cents = parsed.page_price_cents
            parsed.coupon_discount_cents = None
            for item in parsed.coupon_breakdown:
                item["applied"] = False
            parsed.confidence = "high"
            parsed.error = None
        if require_primary and not (primary_text or anchored_body):
            parsed.confidence = "low"
        if (
            not require_primary
            and ("国补" in price_body or "补贴" in price_body)
            and not explicit_final_price
            and (promo_price is None or promo_price >= (parsed.page_price_cents or 0))
        ):
            parsed.confidence = "low"
        logger.info(
            "JD listing {} price: page={}, estimated={}, confidence={}, final_label={}, promo={}",
            listing.id,
            parsed.page_price_cents,
            parsed.estimated_price_cents,
            parsed.confidence,
            explicit_final_price and not rejected_final_price,
            promo_price,
        )

        effective = parsed.estimated_price_cents or parsed.page_price_cents or 0
        status = parsed.status
        if status == "ok" and effective <= 0:
            status = "parse_error"
        if parsed.page_price_cents and effective * 4 < parsed.page_price_cents:
            parsed.confidence = "low"
            parsed.error = "页面预估价远低于同页标价，本轮价格未采纳"

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

    async def fetch_checkout_price(
        self,
        listing: Listing,
        account: Account,
        headless: bool = False,
    ) -> PriceQuote:
        """Read the payable amount on the order confirmation page.

        Manual calls use a visible browser so the user can clear a verification
        or finish the navigation. Automatic calls run headless and give up
        quietly. This method never clicks "提交订单" or any payment button.
        """
        wait_seconds = 30 if headless else 180
        page_session = (
            self.browser.session(account.profile_dir, headless=True)
            if headless
            else self.browser.resident_session(account.profile_dir)
        )
        async with page_session as page:
            await self._goto(page, prefer_mobile_url(listing.url))
            await _click_exact_text(page, "立即购买")

            # Mobile "buy now" frequently lands on trade.m.jd.com's risk page.
            # Retry from the desktop item page once; the user can still finish
            # the navigation in the visible window.
            await page.wait_for_timeout(2_500)
            early_body = ""
            with suppress(Exception):
                early_body = await page.locator("body").inner_text(timeout=5_000)
            if "limit.html" in page.url or "活动火爆" in early_body:
                sku = extract_sku(listing.url)
                if sku is not None:
                    with suppress(Exception):
                        await page.goto(
                            f"https://item.jd.com/{sku}.html",
                            wait_until="domcontentloaded",
                            timeout=60_000,
                        )
                        await page.wait_for_timeout(1_500)
                        await _click_exact_text(page, "立即购买")

            deadline = asyncio.get_running_loop().time() + wait_seconds
            while asyncio.get_running_loop().time() < deadline:
                if page.is_closed():
                    raise ParseError("结算窗口已关闭")
                try:
                    body = await page.locator("body").inner_text(timeout=10_000)
                except Exception:
                    body = ""
                if "passport.jd.com" in page.url or "请登录" in body:
                    raise LoginRequired("京东登录态失效，请重新登录")

                on_order_page = "trade.jd.com" in page.url or "提交订单" in body
                if on_order_page:
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
            "没有在结算预览页读到应付金额；京东可能限流或需要人工操作，请重试"
        )

    async def get_sku_variants(
        self,
        url: str,
        account: Account,
    ) -> tuple[str, list[SkuVariant]]:
        async with self.browser.resident_session(account.profile_dir) as page:
            await self._goto(page, prefer_mobile_url(normalize_url(url)))
            final_url = page.url
            title, body, _price_texts, _shop_texts, _coupon_texts = await self._read_page(page)
            self._assert_not_blocked(final_url, title, body)
            if len(body.strip()) < 40:
                raise CaptchaRequired("京东页面没有加载出内容，可能被限流，请稍后重试")
            html = await page.content()
            return title, parse_sku_variants(html)

    async def login(self, account: Account) -> LoginStatus:
        async with self.browser.resident_session(account.profile_dir) as page:
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
                    return LoginStatus(
                        logged_in=True,
                        message="京东登录成功",
                        display_name=(
                            _cookie_value(cookies, "unick")
                            or _cookie_value(cookies, "pin")
                        ),
                    )
                await page.wait_for_timeout(2000)
        raise LoginRequired("登录超时，请重新发起登录")

    async def open_verification(self, listing: Listing, account: Account) -> LoginStatus:
        """Open a headed JD page and wait for the user to clear a verification."""
        async with self.browser.resident_session(account.profile_dir) as page:
            await page.goto(
                f"https://item.jd.com/{listing.platform_item_id}.html",
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
        async with self.browser.resident_session(account.profile_dir) as page:
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
                display_name=(
                    (_cookie_value(cookies, "unick") or _cookie_value(cookies, "pin"))
                    if logged_in
                    else None
                ),
            )

    async def _goto(self, page: Page, url: str) -> Response | None:
        response = await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        # Mobile JD pages render the price asynchronously. Wait for a visible
        # currency amount instead of relying on a fixed sleep.
        with suppress(Exception):
            await page.wait_for_function(
                "() => /[¥￥]\\s*[0-9]/.test(document.body.innerText)",
                timeout=8_000,
            )
        await page.wait_for_timeout(1_000)
        return response

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
            raise RateLimited("京东 PC 商品页频控，本轮未采价；下轮自动重试")
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
            raise RateLimited("京东访问频繁，本轮未采价；下轮自动重试")
        if "risk_handler" in url or "京东验证" in title or "验证一下" in body:
            raise CaptchaRequired("京东触发验证，请稍后重试或手动登录")
        if "passport.jd.com" in url:
            raise LoginRequired("京东登录态失效，请重新登录")


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


def _title_anchored_product_section(body: str, title: str) -> str:
    """Find the product details adjoining the monitored title."""
    normalized_body = re.sub(r"\s+", " ", body)
    normalized_title = clean_title(title)
    for length in (36, 28, 20):
        if len(normalized_title) < length:
            continue
        start = normalized_body.find(normalized_title[:length])
        if start < 0:
            continue
        section = normalized_body[start + length : start + length + 2500]
        for boundary in ("商品详情", "猜你喜欢", "为你推荐", "看了又看"):
            boundary_at = section.find(boundary)
            if boundary_at >= 0:
                section = section[:boundary_at]
        return section
    return ""


def _title_anchored_price_context(section: str) -> str:
    """Use the first non-coupon currency amount beside the product title."""
    nearby = section[:650]
    for match in ANY_PRICE_RE.finditer(nearby):
        prefix = nearby[max(0, match.start() - 12) : match.start()]
        if any(word in prefix for word in ("领后减", "领券后减", "优惠券", "满减")):
            continue
        return section[match.start() : match.start() + 500]
    return ""


def clean_title(title: str) -> str:
    value = re.sub(r"【图片\s*价格\s*品牌\s*评论】", "", title or "")
    value = re.sub(r"[-_|]\s*京东\s*$", "", value.strip())
    return re.sub(r"\s+", " ", value).strip()


def parse_specs(title: str) -> dict[str, str]:
    specs: dict[str, str] = {}
    match = re.search(r"(\d{1,3})\s*GB\s*(?:\+| )\s*(\d{1,4})\s*GB", title, re.IGNORECASE)
    if match:
        specs["ram_gb"] = match.group(1)
        specs["storage_gb"] = match.group(2)
    return specs
