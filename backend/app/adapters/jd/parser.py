from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from app.adapters.base import QuoteStatus, ShopType

PRICE_NUMBER = r"([0-9][0-9,]*(?:\.[0-9]{1,2})?)"
TO_PRICE_RE = re.compile(rf"到手价[^\d]{{0,12}}{PRICE_NUMBER}")
JD_PRICE_RE = re.compile(rf"京东价[^\d]{{0,12}}{PRICE_NUMBER}")
ANY_PRICE_RE = re.compile(rf"(?:¥|￥)\s*{PRICE_NUMBER}")
COUPON_THRESHOLD_RE = re.compile(r"满\s*([0-9][0-9,]*)\s*减\s*([0-9][0-9,]*)")
COUPON_AMOUNT_RE = re.compile(r"([0-9][0-9,]*)\s*元(?:优惠券|券)")
NOISE_PRICE_WORDS = ("月", "白条", "定金", "首付", "每期", "分期")
NOISE_PRICE_RE = re.compile(r"\d+\s*期")
EMBEDDED_PRICE_RE = re.compile(
    r'"priceFloor"\s*:\s*\{.*?"ext"\s*:\s*\{.*?"jdPrice"\s*:\s*"([0-9]+(?:\.[0-9]{1,2})?)"',
    re.DOTALL,
)
EMBEDDED_JD_PRICE_RE = re.compile(r'"jdPrice"\s*:\s*"([0-9]+(?:\.[0-9]{1,2})?)"')


@dataclass(frozen=True)
class SkuVariant:
    color: str
    size: str
    spec: str
    sku_id: str
    url: str
    ram_gb: int | None
    storage_gb: int | None


@dataclass
class ParsedProduct:
    title: str
    shop_name: str
    shop_type: ShopType
    evidence: dict[str, str] = field(default_factory=dict)
    page_price_cents: int | None = None
    estimated_price_cents: int | None = None
    coupon_discount_cents: int | None = None
    coupon_breakdown: list[dict] = field(default_factory=list)
    shipping_cents: int = 0
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

    if page_price_cents is not None:
        total = min(total, max(0, page_price_cents - 1))
    return total, breakdown


def _detect_shop(shop_texts: Iterable[str], body_text: str) -> tuple[str, ShopType, dict[str, str]]:
    texts = [text.strip() for text in shop_texts if text.strip()]
    shop_blob = " ".join(texts)
    combined = f"{shop_blob} {body_text}"

    if "京东自营" in combined or any("自营" in text for text in texts):
        shop_name = next(
            (text.splitlines()[0].strip() for text in texts if text.strip()),
            "京东自营",
        )
        return shop_name, "jd_official_self", {"self_operated": "true"}

    if "官方旗舰店" in combined:
        official_match = re.search(r"([A-Za-z0-9一-龥]+官方旗舰店)", combined)
        shop_name = (
            official_match.group(1)
            if official_match
            else next(
                (text for text in texts if "旗舰店" in text),
                texts[0] if texts else "官方旗舰店",
            )
        )
        return shop_name, "official_flagship", {"official_badge": "true"}

    if "旗舰店" in combined:
        shop_name = next((text for text in texts if "旗舰店" in text), texts[0] if texts else "旗舰店")
        return shop_name, "unknown", {"official_badge": "false"}

    if any(word in combined for word in ("专卖店", "专营店", "小店")):
        shop_name = texts[0] if texts else "其他店铺"
        return shop_name, "other", {"official_badge": "false"}

    shop_name = texts[0] if texts else "未知店铺"
    return shop_name, "unknown", {}


SKU_ID_RE = re.compile(r'"skuId"\s*:\s*"(\d{6,})"')
SIZE_RE = re.compile(r"(\d{1,3})\s*GB\s*\+\s*(\d{2,4})\s*GB", re.IGNORECASE)


def parse_sku_variants(html: str) -> list[SkuVariant]:
    variants: list[SkuVariant] = []
    seen: set[str] = set()
    for match in SKU_ID_RE.finditer(html):
        sku_id = match.group(1)
        if sku_id in seen:
            continue
        start = html.rfind("{", 0, match.start())
        end = html.find("}", match.end())
        if start < 0 or end < 0:
            continue
        try:
            payload = json.loads(html[start : end + 1])
        except (ValueError, TypeError):
            continue
        if str(payload.get("skuId") or "") != sku_id:
            continue
        size = str(payload.get("size") or "")
        size_match = SIZE_RE.search(size)
        if size_match is None:
            continue
        seen.add(sku_id)
        variants.append(
            SkuVariant(
                color=str(payload.get("color") or ""),
                size=size,
                spec=str(payload.get("spec") or ""),
                sku_id=sku_id,
                url=f"https://item.m.jd.com/product/{sku_id}.html",
                ram_gb=int(size_match.group(1)),
                storage_gb=int(size_match.group(2)),
            )
        )
    return variants


def extract_embedded_price_cents(html: str) -> int | None:
    match = EMBEDDED_PRICE_RE.search(html)
    if match:
        return parse_price_cents(match.group(1))
    for value in EMBEDDED_JD_PRICE_RE.findall(html):
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
) -> ParsedProduct:
    title = re.sub(r"\s+", " ", title or "").strip()
    body_text = body_text or ""
    prices = list(price_texts)
    shop_name, shop_type, evidence = _detect_shop(shop_texts, body_text)

    if "risk_handler" in url or "京东验证" in title or "验证一下" in body_text:
        return ParsedProduct(
            title=title or "京东验证",
            shop_name=shop_name,
            shop_type=shop_type,
            evidence=evidence,
            status="captcha",
            error="京东触发验证，请稍后重试或手动登录",
        )
    if "passport.jd.com" in url or "请登录" in body_text:
        return ParsedProduct(
            title=title or "请登录",
            shop_name=shop_name,
            shop_type=shop_type,
            evidence=evidence,
            status="login_required",
            error="京东登录态失效，请重新登录",
        )

    to_match = TO_PRICE_RE.search(body_text)
    jd_match = JD_PRICE_RE.search(body_text)
    estimated_from_label = parse_price_cents(to_match.group(1)) if to_match else None
    jd_price = parse_price_cents(jd_match.group(1)) if jd_match else None
    page_price = jd_price or _first_plausible_price(prices)
    if page_price is None:
        page_price = _first_plausible_price([body_text])
    if page_price is None:
        page_price = embedded_price_cents

    if estimated_from_label is not None:
        coupon_total = 0
        _, breakdown = _parse_coupons(body_text, page_price)
        if page_price is not None and page_price > estimated_from_label:
            coupon_total = page_price - estimated_from_label
        elif page_price is None:
            page_price = estimated_from_label
        return ParsedProduct(
            title=title,
            shop_name=shop_name,
            shop_type=shop_type,
            evidence=evidence,
            page_price_cents=page_price,
            estimated_price_cents=estimated_from_label,
            coupon_discount_cents=coupon_total,
            coupon_breakdown=breakdown,
            status="ok",
        )

    if page_price is None:
        return ParsedProduct(
            title=title,
            shop_name=shop_name,
            shop_type=shop_type,
            evidence=evidence,
            status="parse_error",
            error="没有在页面上找到可识别的价格",
        )

    coupon_total, breakdown = _parse_coupons(body_text, page_price)
    estimated = max(0, page_price - coupon_total)
    return ParsedProduct(
        title=title,
        shop_name=shop_name,
        shop_type=shop_type,
        evidence=evidence,
        page_price_cents=page_price,
        estimated_price_cents=estimated,
        coupon_discount_cents=coupon_total,
        coupon_breakdown=breakdown,
        status="ok",
    )


def extract_sku(url: str) -> str | None:
    patterns = (
        r"item\.jd\.com/(\d+)\.html",
        r"item\.m\.jd\.com/product/(\d+)\.html",
        r"/(\d+)\.html",
    )
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None
