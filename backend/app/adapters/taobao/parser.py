from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from urllib.parse import parse_qs, urlparse

from app.adapters.base import PriceConfidence, QuoteStatus, ShopType

PRICE_NUMBER = r"([0-9][0-9,]*(?:\.[0-9]{1,2})?)"
AFTER_COUPON_RE = re.compile(
    rf"(?:券后价?|到手价|折后价|优惠价|促销价|活动价|补贴后价?|补贴价|政府补贴后)"
    rf"[^\d]{{0,12}}{PRICE_NUMBER}"
)
ORIGINAL_PRICE_RE = re.compile(
    rf"(?:原价|划线价|专柜价|日常价|优惠前)[^\d]{{0,12}}{PRICE_NUMBER}"
)
ANY_PRICE_RE = re.compile(rf"(?:¥|￥)\s*{PRICE_NUMBER}")
COUPON_THRESHOLD_RE = re.compile(r"满\s*([0-9][0-9,]*)\s*元?\s*减\s*([0-9][0-9,]*)")
COUPON_AMOUNT_RE = re.compile(r"([0-9][0-9,]*)\s*元(?:优惠券|店铺券|券)")
PROMOTION_AMOUNT_RE = re.compile(
    r"(?:闪电加补|加补|立减|直降|补贴)[^\d]{0,6}([0-9][0-9,]*)\s*元"
)
GOV_SUBSIDY_PERCENT_RE = re.compile(
    r"(?:政府补贴|国家补贴)\s*([0-9]{1,2}(?:\.[0-9])?)\s*%"
)
DEGRADED_PAGE_PHRASES = (
    "访问异常提示",
    "系统检测到当前访问存在异常",
)
NOISE_PRICE_WORDS = (
    "月",
    "花呗",
    "分期",
    "定金",
    "首付",
    "每期",
    "淘金币",
    "原价",
    "划线价",
    "专柜价",
    "日常价",
)
NOISE_PRICE_RE = re.compile(r"\d+\s*期")
OFFICIAL_SHOP_RE = re.compile(r"([A-Za-z0-9一-龥()（）·&]{2,40}官方旗舰店)")
ITEM_ID_RE = re.compile(r"(?:[?&](?:id|itemId|item_id)=)(\d{5,})")
PAYABLE_RE = re.compile(
    rf"(?:实付款|应付总额|应付金额|需付款|合计)[^\d]{{0,12}}{PRICE_NUMBER}"
)
EMBEDDED_PRICE_PATTERNS = (
    re.compile(
        r'"(?:promotionPrice|promoPrice|salePrice|defaultItemPrice|itemPrice|'
        r'finalPrice|subPrice|skuPrice)"\s*:\s*"([0-9]+(?:\.[0-9]{1,2})?)"'
    ),
    re.compile(rf'"priceText"\s*:\s*"[¥￥]?\s*{PRICE_NUMBER}"'),
    re.compile(r'"price"\s*:\s*"([0-9]+(?:\.[0-9]{1,2})?)"'),
)
SHOP_NAME_JSON_RE = re.compile(r'"shopName"\s*:\s*"([^"]{2,80})"')


GENERIC_TITLES = {
    "商品详情",
    "商品详情页",
    "淘宝",
    "天猫",
    "淘宝网",
    "登录",
    "登录页面",
    "验证码拦截",
}
TITLE_NOISE_WORDS = (
    "用户评价",
    "参数信息",
    "图文详情",
    "本店推荐",
    "看了又看",
    "好评率",
    "访问异常",
    "优惠前",
    "可开发票",
    "已售",
)


def choose_title(document_title: str, title_texts: Iterable[str] = ()) -> str:
    """Pick the real product title from the document title and DOM titles.

    Tmall's SPA can keep ``document.title`` at "商品详情" until late in
    hydration, while the real title is already rendered in a heading-like
    element. Prefer the longest non-generic candidate.
    """
    candidates = [document_title or "", *title_texts]
    cleaned = [
        re.sub(r"\s+", " ", value).strip()
        for value in candidates
        if value and value.strip()
    ]
    valid = [
        value
        for value in cleaned
        if len(value) >= 8
        and value not in GENERIC_TITLES
        and not any(word in value for word in TITLE_NOISE_WORDS)
    ]
    if not valid:
        return cleaned[0] if cleaned else ""
    title = max(valid, key=len)
    title = re.sub(
        r"\s*[-|_]\s*(?:tmall\.com|淘宝网|淘宝|天猫).*$",
        "",
        title,
        flags=re.IGNORECASE,
    )
    return title.strip()[:250]


@dataclass
class ParsedTaobaoProduct:
    title: str
    shop_name: str
    shop_type: ShopType
    evidence: dict[str, str] = field(default_factory=dict)
    page_price_cents: int | None = None
    estimated_price_cents: int | None = None
    coupon_discount_cents: int | None = None
    coupon_breakdown: list[dict] = field(default_factory=list)
    shipping_cents: int = 0
    confidence: PriceConfidence | None = None
    status: QuoteStatus = "ok"
    error: str | None = None


def parse_price_cents(text: str) -> int | None:
    match = re.search(PRICE_NUMBER, text.replace("，", ","))
    if not match:
        return None
    try:
        value = Decimal(match.group(1).replace(",", ""))
    except InvalidOperation:
        return None
    cents = int(value * 100)
    if cents < 100 or cents > 10_000_000:
        return None
    return cents


def _first_plausible_price(texts: Iterable[str]) -> int | None:
    for text in texts:
        for match in ANY_PRICE_RE.finditer(text):
            start, end = match.span()
            context = text[max(0, start - 8) : min(len(text), end + 8)]
            if any(word in context for word in NOISE_PRICE_WORDS):
                continue
            if NOISE_PRICE_RE.search(context):
                continue
            cents = parse_price_cents(match.group(1))
            if cents is not None:
                return cents
    return None


def _parse_coupons(text: str, page_price_cents: int | None) -> tuple[int, list[dict]]:
    breakdown: list[dict] = []
    seen: set[str] = set()
    total = 0

    for match in COUPON_THRESHOLD_RE.finditer(text):
        raw = match.group(0)
        if raw in seen:
            continue
        seen.add(raw)
        threshold = parse_price_cents(match.group(1))
        amount = parse_price_cents(match.group(2))
        if threshold is None or amount is None:
            continue
        applicable = page_price_cents is not None and page_price_cents >= threshold
        breakdown.append(
            {
                "type": "满减",
                "raw": raw,
                "threshold_cents": threshold,
                "amount_cents": amount,
                "applied": applicable,
            }
        )
        if applicable:
            total += amount

    for match in COUPON_AMOUNT_RE.finditer(text):
        raw = match.group(0)
        if raw in seen:
            continue
        seen.add(raw)
        amount = parse_price_cents(match.group(1))
        if amount is None:
            continue
        applicable = page_price_cents is not None and page_price_cents > amount
        breakdown.append(
            {
                "type": "优惠券",
                "raw": raw,
                "threshold_cents": None,
                "amount_cents": amount,
                "applied": applicable,
            }
        )
        if applicable:
            total += amount

    for match in PROMOTION_AMOUNT_RE.finditer(text):
        raw = match.group(0)
        if raw in seen:
            continue
        seen.add(raw)
        amount = parse_price_cents(match.group(1))
        if amount is None:
            continue
        applicable = page_price_cents is not None and page_price_cents > amount
        breakdown.append(
            {
                "type": "立减/补贴",
                "raw": raw,
                "threshold_cents": None,
                "amount_cents": amount,
                "applied": applicable,
            }
        )
        if applicable:
            total += amount

    for match in GOV_SUBSIDY_PERCENT_RE.finditer(text):
        raw = match.group(0)
        if raw in seen:
            continue
        seen.add(raw)
        try:
            percent = float(match.group(1))
        except ValueError:
            continue
        breakdown.append(
            {
                "type": "政府补贴",
                "raw": raw,
                "percent": percent,
                "threshold_cents": None,
                "amount_cents": None,
                "applied": True,
            }
        )

    if page_price_cents is not None:
        total = min(total, max(0, page_price_cents - 1))
    return total, breakdown


def _detect_shop(
    shop_texts: Iterable[str],
    title: str,
    body_text: str,
) -> tuple[str, ShopType, dict[str, str]]:
    texts = [text.strip() for text in shop_texts if text.strip()]
    shop_blob = " ".join(texts)
    body_lines = [line.strip() for line in body_text.splitlines() if line.strip()]

    match = OFFICIAL_SHOP_RE.search(shop_blob)
    if match:
        return match.group(1), "official_flagship", {
            "official_badge": "true",
            "badge_text": "官方旗舰店",
        }
    shop_line = next((line for line in texts if "官方旗舰店" in line), None)
    if shop_line:
        return shop_line[:80], "official_flagship", {
            "official_badge": "true",
            "badge_text": "官方旗舰店",
        }

    if "官方旗舰店" in shop_blob:
        return shop_blob[:80], "official_flagship", {
            "official_badge": "true",
            "badge_text": "官方旗舰店",
        }

    # Shop name elements are the authoritative source. Fall back to short body
    # lines (shop card) but never to the item title, which sellers can stuff
    # with "官方旗舰店" even when the seller is a reseller.
    candidates = [line for line in body_lines if len(line) <= 40 and "官方旗舰店" in line]
    if candidates:
        name = candidates[0]
        return name, "official_flagship", {
            "official_badge": "true",
            "badge_text": "官方旗舰店",
        }

    if any("旗舰店" in line for line in texts):
        shop_name = next(line for line in texts if "旗舰店" in line)
        return shop_name[:80], "unknown", {"official_badge": "false"}
    if "旗舰店" in shop_blob:
        return shop_blob[:80], "unknown", {"official_badge": "false"}

    if any(word in shop_blob for word in ("专营店", "专卖店", "企业店", "个体户", "小店")):
        return texts[0][:80] if texts else "其他店铺", "other", {"official_badge": "false"}

    if any(word in title for word in ("专卖店", "专营店")):
        return texts[0][:80] if texts else "其他店铺", "other", {"official_badge": "false"}

    return texts[0][:80] if texts else "未知店铺", "unknown", {}


def extract_item_id(url: str) -> str | None:
    match = ITEM_ID_RE.search(url)
    if match:
        return match.group(1)
    parsed = urlparse(url)
    values = parse_qs(parsed.query).get("id")
    if values and values[0].isdigit():
        return values[0]
    return None


def extract_sku_id(url: str) -> str | None:
    query = parse_qs(urlparse(url).query)
    for key in ("skuId", "sku_id"):
        values = query.get(key)
        if values and values[0].isdigit():
            return values[0]
    return None


def parse_checkout_payable_cents(text: str) -> int | None:
    match = PAYABLE_RE.search(text or "")
    if match:
        return parse_price_cents(match.group(1))
    return None


def extract_ice_context(html: str) -> dict | None:
    marker = "window.__ICE_APP_CONTEXT__"
    index = html.find(marker)
    if index >= 0:
        # The page can contain `window.__ICE_APP_CONTEXT__ || {}` followed by
        # `var b = {...}` and a later `window.__ICE_APP_CONTEXT__ = b`.
        # Try candidate JSON objects after the marker and pick the one that
        # looks like the SSR payload.
        decoder = json.JSONDecoder()
        search_from = index
        for _ in range(20):
            start = html.find("{", search_from)
            if start < 0:
                break
            search_from = start + 1
            try:
                value, _end = decoder.raw_decode(html[start:])
            except (ValueError, TypeError):
                continue
            if isinstance(value, dict) and (
                "loaderData" in value or "appData" in value
            ):
                return value
    match = re.search(
        r'<script[^>]+id=["\']__ICE_APP_CONTEXT__["\'][^>]*>(.*?)</script>',
        html,
        re.DOTALL,
    )
    if match:
        try:
            value = json.loads(match.group(1))
        except (ValueError, TypeError):
            return None
        return value if isinstance(value, dict) else None
    return None


@dataclass(frozen=True)
class SsrSkuInfo:
    price_cents: int | None
    price_title: str
    sub_price_cents: int | None
    sub_price_title: str
    stock_text: str
    quantity: int | None
    limit: int | None


def extract_ssr_sku_info(html: str, sku_id: str | None) -> SsrSkuInfo | None:
    if not sku_id:
        return None
    context = extract_ice_context(html)
    if context is None:
        return None

    def walk(value: object) -> dict | None:
        if isinstance(value, dict):
            sku2info = value.get("sku2info")
            if isinstance(sku2info, dict):
                entry = sku2info.get(sku_id)
                if isinstance(entry, dict):
                    return entry
            for child in value.values():
                found = walk(child)
                if found is not None:
                    return found
        elif isinstance(value, list):
            for child in value:
                found = walk(child)
                if found is not None:
                    return found
        return None

    entry = walk(context)
    if entry is None:
        return None
    price = entry.get("price") if isinstance(entry.get("price"), dict) else {}
    price_cents = None
    for key in ("priceMoney", "priceText"):
        raw = str(price.get(key) or "")
        cents = parse_price_cents(raw)
        if cents is not None:
            price_cents = cents
            break
    sub_price = entry.get("subPrice") if isinstance(entry.get("subPrice"), dict) else {}
    sub_price_cents = None
    for key in ("priceMoney", "priceText"):
        raw = str(sub_price.get(key) or "")
        cents = parse_price_cents(raw)
        if cents is not None:
            sub_price_cents = cents
            break
    quantity = entry.get("quantity")
    limit = entry.get("limit")
    return SsrSkuInfo(
        price_cents=price_cents,
        price_title=str(price.get("priceTitle") or ""),
        sub_price_cents=sub_price_cents,
        sub_price_title=str(sub_price.get("priceTitle") or ""),
        stock_text=str(entry.get("quantityText") or ""),
        quantity=_int_or_none(quantity),
        limit=_int_or_none(limit),
    )


def _int_or_none(value: object) -> int | None:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def extract_ssr_sku_price_cents(html: str, sku_id: str | None) -> int | None:
    info = extract_ssr_sku_info(html, sku_id)
    if info is None:
        return None
    return info.sub_price_cents or info.price_cents


def extract_embedded_shop_name(html: str) -> str | None:
    match = SHOP_NAME_JSON_RE.search(html)
    if match:
        value = match.group(1).strip()
        if value and value != "null":
            return value
    return None


def extract_embedded_price_cents(html: str) -> int | None:
    for pattern in EMBEDDED_PRICE_PATTERNS:
        for value in pattern.findall(html):
            cents = parse_price_cents(value)
            if cents is not None:
                return cents
    return None


def parse_product_page(
    *,
    url: str,
    title: str,
    body_text: str,
    price_texts: Iterable[str] = (),
    shop_texts: Iterable[str] = (),
    embedded_price_cents: int | None = None,
) -> ParsedTaobaoProduct:
    title = re.sub(r"\s+", " ", title or "").strip()
    body_text = body_text or ""
    shop_name, shop_type, evidence = _detect_shop(shop_texts, title, body_text)

    if "_____tmd_____" in url or "/punish" in url or "验证码拦截" in title:
        return ParsedTaobaoProduct(
            title=title or "淘宝验证",
            shop_name=shop_name,
            shop_type=shop_type,
            evidence=evidence,
            status="captcha",
            error="淘宝触发验证，请打开验证页完成滑块",
        )
    if "login.taobao.com" in url or "login.tmall.com" in url:
        return ParsedTaobaoProduct(
            title=title or "请登录",
            shop_name=shop_name,
            shop_type=shop_type,
            evidence=evidence,
            status="login_required",
            error="淘宝登录态失效，请重新登录",
        )
    if any(phrase in body_text for phrase in DEGRADED_PAGE_PHRASES):
        return ParsedTaobaoProduct(
            title=title,
            shop_name=shop_name,
            shop_type=shop_type,
            evidence=evidence,
            status="parse_error",
            error=(
                "淘宝页面处于访问异常/降级状态，补贴和优惠可能未展示，"
                "本次不采用该页面价格；请先确认账号与浏览器一致并稍后重试"
            ),
        )

    estimated_from_label = None
    match = AFTER_COUPON_RE.search(body_text)
    if match:
        estimated_from_label = parse_price_cents(match.group(1))

    original_from_label = None
    match = ORIGINAL_PRICE_RE.search(body_text)
    if match:
        original_from_label = parse_price_cents(match.group(1))

    prices = list(price_texts)
    selector_price = _first_plausible_price(prices)
    body_price = _first_plausible_price([body_text])
    page_price = selector_price or body_price
    page_confidence: PriceConfidence = "low"
    if (
        selector_price is not None
        and body_price is not None
        and body_price < selector_price
    ):
        # Price blocks often put the struck-through original price first;
        # the body text has the actual sale price.
        page_price = body_price
    if page_price is None:
        page_price = original_from_label
    if page_price is None:
        page_price = embedded_price_cents
    if (
        estimated_from_label is not None
        and original_from_label is not None
        and original_from_label > estimated_from_label
    ):
        # The page's pre-discount price is the baseline; the subsidy/coupon
        # label is the estimated payable.
        page_price = original_from_label

    if "亲，请登录" in body_text and page_price is None and estimated_from_label is None:
        return ParsedTaobaoProduct(
            title=title or "请登录",
            shop_name=shop_name,
            shop_type=shop_type,
            evidence=evidence,
            status="login_required",
            error="淘宝登录态失效，请重新登录",
        )

    if estimated_from_label is not None:
        coupon_total = 0
        _, breakdown = _parse_coupons(body_text, page_price)
        if page_price is not None and page_price > estimated_from_label:
            coupon_total = page_price - estimated_from_label
        elif page_price is None:
            page_price = estimated_from_label
        return ParsedTaobaoProduct(
            title=title,
            shop_name=shop_name,
            shop_type=shop_type,
            evidence=evidence,
            page_price_cents=page_price,
            estimated_price_cents=estimated_from_label,
            coupon_discount_cents=coupon_total,
            coupon_breakdown=breakdown,
            confidence="high",
            status="ok",
        )

    if page_price is None:
        return ParsedTaobaoProduct(
            title=title,
            shop_name=shop_name,
            shop_type=shop_type,
            evidence=evidence,
            status="parse_error",
            error="没有在淘宝页面上找到可识别的价格",
        )

    coupon_total, breakdown = _parse_coupons(body_text, page_price)
    estimated = max(0, page_price - coupon_total)
    return ParsedTaobaoProduct(
        title=title,
        shop_name=shop_name,
        shop_type=shop_type,
        evidence=evidence,
        page_price_cents=page_price,
        estimated_price_cents=estimated,
        coupon_discount_cents=coupon_total,
        coupon_breakdown=breakdown,
        confidence=page_confidence,
        status="ok",
    )
