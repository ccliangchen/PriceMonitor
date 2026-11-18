from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from app.adapters.base import PriceConfidence, QuoteStatus, ShopType

PRICE_NUMBER = r"([0-9][0-9,]*(?:\.[0-9]{1,2})?)"
TO_PRICE_RE = re.compile(rf"到手价[^\d]{{0,12}}{PRICE_NUMBER}")
FINAL_PRICE_LABEL_RE = re.compile(
    rf"(?:预估到手价|预计到手价|国补领后价|国补后价|国补价|补贴后价|券后价|到手价|实付价)"
    rf"[^\d]{{0,16}}{PRICE_NUMBER}"
)
JD_PRICE_RE = re.compile(rf"京东价[^\d]{{0,12}}{PRICE_NUMBER}")
ANY_PRICE_RE = re.compile(rf"(?:¥|￥)\s*{PRICE_NUMBER}")
COUPON_THRESHOLD_RE = re.compile(r"满\s*([0-9][0-9,]*)\s*减\s*([0-9][0-9,]*)")
COUPON_AMOUNT_RE = re.compile(r"([0-9][0-9,]*)\s*元(?:优惠券|券)")
PROMOTION_AMOUNT_RE = re.compile(
    r"(?:立减|直降|补贴|返现)[^\d]{0,6}([0-9][0-9,]*)\s*元"
)
CLAIM_DISCOUNT_RE = re.compile(
    rf"(?:领后减|领券后减)[^\d]{{0,6}}(?:¥|￥)?\s*{PRICE_NUMBER}"
)
APPLIED_DISCOUNT_SECTION_RE = re.compile(r"已享受?[：:]")
NOISE_PRICE_WORDS = ("月", "白条", "定金", "首付", "每期", "分期")
NOISE_PRICE_RE = re.compile(r"\d+\s*期")
EMBEDDED_PRICE_RE = re.compile(
    r'"priceFloor"\s*:\s*\{.*?"ext"\s*:\s*\{.*?"jdPrice"\s*:\s*"([0-9]+(?:\.[0-9]{1,2})?)"',
    re.DOTALL,
)
EMBEDDED_JD_PRICE_RE = re.compile(r'"jdPrice"\s*:\s*"([0-9]+(?:\.[0-9]{1,2})?)"')
PAYABLE_RE = re.compile(
    rf"(?:应付总额|应付金额|需付款|实付款|应付)[^\d]{{0,12}}{PRICE_NUMBER}"
)


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
    seen_discounts: set[tuple[str, int]] = set()
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

    for match in CLAIM_DISCOUNT_RE.finditer(text):
        raw = match.group(0)
        if raw in seen:
            continue
        seen.add(raw)
        amount = parse_price_cents(match.group(1))
        if amount is None:
            continue
        # The same JD benefit often appears twice with different currency
        # glyphs (¥ and ￥). Its wording is not a stacking guarantee.
        if ("领后减", amount) in seen_discounts:
            continue
        seen_discounts.add(("领后减", amount))
        applicable = page_price_cents is not None and page_price_cents > amount
        breakdown.append(
            {
                "type": "领后减",
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
    # The whole page also contains recommended shops. Use the actual seller
    # element when available; body text is only a fallback for older layouts.
    combined = shop_blob if texts else body_text
    if not texts and "京东自营" in combined and "官方旗舰店" in combined:
        return "未知店铺", "unknown", {}

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


def parse_checkout_payable_cents(text: str) -> int | None:
    match = PAYABLE_RE.search(text or "")
    if match:
        return parse_price_cents(match.group(1))
    return None


def extract_embedded_promotion_price_cents(html: str) -> int | None:
    """Read JD's promo/seckill JSON when the page has no "到手价" label."""
    decoder = json.JSONDecoder()
    prices: list[int] = []

    index = html.find('"promov2"')
    if index >= 0:
        start = html.find("[", index)
        if start >= 0:
            try:
                data, _end = decoder.raw_decode(html[start:])
            except (ValueError, TypeError):
                data = None
            if isinstance(data, list):
                for item in data:
                    if not isinstance(item, dict):
                        continue
                    for pi in item.get("pis") or []:
                        if not isinstance(pi, dict):
                            continue
                        custom = pi.get("customtag")
                        if isinstance(custom, str):
                            try:
                                custom = json.loads(custom)
                            except (ValueError, TypeError):
                                custom = {}
                        if isinstance(custom, dict):
                            cents = parse_price_cents(str(custom.get("p") or ""))
                            if cents is not None:
                                prices.append(cents)

    index = html.find('"seckill"')
    if index >= 0:
        start = html.find("{", index)
        if start >= 0:
            try:
                data, _end = decoder.raw_decode(html[start:])
            except (ValueError, TypeError):
                data = None
            if isinstance(data, dict) and str(
                data.get("promotionStatus") or "true"
            ).lower() in ("true", "1"):
                for key in ("miaoShaPrice", "jdPrice"):
                    cents = parse_price_cents(str(data.get(key) or ""))
                    if cents is not None:
                        prices.append(cents)

    return min(prices) if prices else None


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
    if "passport.jd.com" in url:
        return ParsedProduct(
            title=title or "请登录",
            shop_name=shop_name,
            shop_type=shop_type,
            evidence=evidence,
            status="login_required",
            error="京东登录态失效，请重新登录",
        )

    final_match = FINAL_PRICE_LABEL_RE.search(body_text)
    jd_match = JD_PRICE_RE.search(body_text)
    estimated_from_label = (
        parse_price_cents(final_match.group(1)) if final_match else None
    )
    jd_price = parse_price_cents(jd_match.group(1)) if jd_match else None
    page_price = jd_price or _first_plausible_price(prices)
    if page_price is None:
        page_price = _first_plausible_price([body_text])
    if page_price is None:
        page_price = embedded_price_cents
    # A promotion label can be stale or inapplicable. A supposed final amount
    # above the current primary price must not override that primary price.
    if (
        estimated_from_label is not None
        and page_price is not None
        and estimated_from_label > page_price
    ):
        estimated_from_label = None

    if estimated_from_label is not None:
        coupon_total = 0
        _, breakdown = _parse_coupons(body_text, page_price)
        # A displayed final amount already includes its promotions. The text
        # alone cannot prove which visible coupons contributed to that amount.
        for item in breakdown:
            item["applied"] = False
        if page_price is not None and page_price > estimated_from_label:
            coupon_total = page_price - estimated_from_label
        elif page_price is None:
            page_price = estimated_from_label
        discount_amounts = {
            item["amount_cents"] for item in breakdown if item["amount_cents"] is not None
        }
        return ParsedProduct(
            title=title,
            shop_name=shop_name,
            shop_type=shop_type,
            evidence=evidence,
            page_price_cents=page_price,
            estimated_price_cents=estimated_from_label,
            coupon_discount_cents=coupon_total,
            coupon_breakdown=breakdown,
            confidence=(
                "low"
                if estimated_from_label in discount_amounts or page_price in discount_amounts
                else "high"
            ),
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
    # A labelled 京东价 is a baseline; listed applied discounts can be
    # subtracted. An unlabeled primary amount beside "已享受" is already the
    # displayed payable estimate and must not be discounted again.
    applied_match = APPLIED_DISCOUNT_SECTION_RE.search(body_text)
    applied_section = applied_match is not None
    labelled_baseline = bool(
        jd_match
        and applied_match
        and 0 <= applied_match.start() - jd_match.end() <= 120
    )
    estimated = (
        page_price
        if applied_section and not labelled_baseline
        else max(0, page_price - coupon_total)
    )
    if applied_section and not labelled_baseline:
        coupon_total = 0
        for item in breakdown:
            item["applied"] = False
    discount_amounts = {
        item["amount_cents"] for item in breakdown if item["amount_cents"] is not None
    }
    return ParsedProduct(
        title=title,
        shop_name=shop_name,
        shop_type=shop_type,
        evidence=evidence,
        page_price_cents=page_price,
        estimated_price_cents=estimated,
        coupon_discount_cents=coupon_total,
        coupon_breakdown=breakdown,
        confidence=(
            "high"
            if coupon_total == 0
            and page_price not in discount_amounts
            and estimated not in discount_amounts
            else "low"
        ),
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
