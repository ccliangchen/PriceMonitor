from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup

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


@dataclass(frozen=True)
class TaobaoSearchItem:
    item_id: str
    title: str
    url: str


@dataclass(frozen=True)
class TaobaoStoreLink:
    name: str
    url: str
    sample_items: tuple[TaobaoSearchItem, ...] = ()


@dataclass(frozen=True)
class TaobaoSkuVariant:
    color: str
    spec: str
    sku_id: str
    url: str
    ram_gb: int | None
    storage_gb: int | None


SHOP_HOST_RE = re.compile(r"^shop\d+\.(?:taobao|tmall)\.com$")
ITEM_LINK_RE = re.compile(r"(?:detail\.tmall\.com|item\.taobao\.com)/item\.htm")
CAPACITY_RE = re.compile(r"(\d{1,3})\s*(TB|T|GB|G)\b", re.IGNORECASE)
COMBINED_CAPACITY_RE = re.compile(
    r"(\d{1,3})\s*(?:GB|G)\s*[+＋]\s*(\d{1,4})\s*(?:GB|G)",
    re.IGNORECASE,
)


def _absolute_href(href: str) -> str:
    value = href.strip()
    if value.startswith("//"):
        return f"https:{value}"
    if value.startswith("item.htm"):
        return f"https://detail.tmall.com/{value}"
    if value.startswith("/"):
        return f"https://detail.tmall.com{value}"
    return value


def _first_line(text: str) -> str:
    return next((line.strip() for line in text.splitlines() if line.strip()), "")


def parse_shop_search_results(html: str) -> list[TaobaoStoreLink]:
    """Extract shop cards from Taobao's ``tab=shop`` search results.

    The anchor for a shop card wraps the shop name, score, fan count and a
    handful of sample items. Only the first non-empty line is the shop name;
    using the whole text would let a sample product title's "官方旗舰店"
    wording leak into shop admission.
    """
    soup = BeautifulSoup(html or "", "lxml")
    results: list[TaobaoStoreLink] = []
    seen: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        url = _absolute_href(str(anchor.get("href") or ""))
        if not SHOP_HOST_RE.fullmatch(urlparse(url).netloc):
            continue
        name = _first_line(anchor.get_text("\n", strip=True))
        name = re.sub(r"\s+", " ", name).strip()
        if not name or len(name) > 80 or "进入店铺" in name:
            continue
        if url in seen:
            continue
        seen.add(url)
        results.append(
            TaobaoStoreLink(
                name=name,
                url=url,
                sample_items=tuple(parse_store_search_items(str(anchor))),
            )
        )
    return results


def _clean_item_title(text: str) -> str:
    value = re.sub(r"\s+", " ", text or "").strip()
    value = re.split(r"[¥￥]", value, maxsplit=1)[0].strip()
    return value[:250]


def parse_store_search_items(html: str) -> list[TaobaoSearchItem]:
    """Extract item cards from a Tmall/Taobao store search page."""
    soup = BeautifulSoup(html or "", "lxml")
    by_item: dict[str, TaobaoSearchItem] = {}
    for anchor in soup.find_all("a", href=True):
        url = _absolute_href(str(anchor.get("href") or ""))
        if not ITEM_LINK_RE.search(url):
            continue
        item_id = extract_item_id(url)
        if item_id is None:
            continue
        title = _clean_item_title(
            anchor.get_text(" ", strip=True) or str(anchor.get("title") or "")
        )
        if len(title) < 6:
            continue
        existing = by_item.get(item_id)
        if existing is None or len(title) > len(existing.title):
            by_item[item_id] = TaobaoSearchItem(
                item_id=item_id,
                title=title,
                url=url,
            )
    return list(by_item.values())


def _context_res(html: str) -> dict:
    context = extract_ice_context(html) or {}
    loader = context.get("loaderData") or {}
    home = loader.get("home") or {}
    data = home.get("data") or {}
    result = data.get("res") or {}
    return result if isinstance(result, dict) else {}


def _capacity_gb(text: str) -> int | None:
    match = CAPACITY_RE.search(text or "")
    if match is None:
        return None
    value = int(match.group(1))
    return value * 1024 if match.group(2).upper().startswith("T") else value


def _find_ram_storage(
    values: dict[str, str],
    prop_names: dict[str, str],
) -> tuple[int | None, int | None]:
    for value in values.values():
        match = COMBINED_CAPACITY_RE.search(value)
        if match:
            return int(match.group(1)), int(match.group(2))

    ram: int | None = None
    storage: int | None = None
    for pid, value in values.items():
        name = prop_names.get(pid, "")
        capacity = _capacity_gb(value)
        if capacity is None:
            continue
        if ram is None and any(word in name for word in ("内存", "运行")):
            ram = capacity
        elif storage is None and any(word in name for word in ("存储", "容量")):
            storage = capacity
    return ram, storage


def extract_taobao_sku_variants(
    html: str,
    item_url: str = "",
) -> list[TaobaoSkuVariant]:
    """Build SKU options from the item page's SSR ``skuBase`` data.

    ``skuBase.props`` maps property ids (color, storage, package) to names,
    while ``skuBase.skus`` gives each SKU's property path. Prices are read
    separately by ``extract_ssr_sku_info`` for the selected SKU.
    """
    result = _context_res(html)
    sku_base = result.get("skuBase") or {}
    props = sku_base.get("props") if isinstance(sku_base, dict) else None
    skus = sku_base.get("skus") if isinstance(sku_base, dict) else None
    if not isinstance(props, list) or not isinstance(skus, list):
        return []

    prop_names: dict[str, str] = {}
    prop_values: dict[str, dict[str, str]] = {}
    for prop in props:
        if not isinstance(prop, dict):
            continue
        pid = str(prop.get("pid") or "")
        if not pid:
            continue
        prop_names[pid] = str(prop.get("name") or "")
        values: dict[str, str] = {}
        value_map = prop.get("valueMap")
        if isinstance(value_map, dict):
            for vid, value in value_map.items():
                if isinstance(value, dict):
                    name = str(value.get("name") or "").strip()
                    if name:
                        values[str(vid)] = name
        for value in prop.get("values") or []:
            if not isinstance(value, dict):
                continue
            vid = str(value.get("vid") or "")
            name = str(value.get("name") or "").strip()
            if vid and name:
                values[vid] = name
        prop_values[pid] = values

    item_id = extract_item_id(item_url) or str((result.get("item") or {}).get("itemId") or "")
    host = "detail.tmall.com" if "tmall.com" in item_url else "item.taobao.com"
    variants: list[TaobaoSkuVariant] = []
    seen: set[str] = set()
    for sku in skus:
        if not isinstance(sku, dict):
            continue
        sku_id = str(sku.get("skuId") or "")
        if not sku_id or sku_id in seen:
            continue
        sku_values: dict[str, str] = {}
        for pair in str(sku.get("propPath") or "").split(";"):
            if ":" not in pair:
                continue
            pid, vid = pair.split(":", 1)
            name = prop_values.get(pid, {}).get(vid)
            if name:
                sku_values[pid] = name

        color = ""
        spec = ""
        for pid, value in sku_values.items():
            name = prop_names.get(pid, "")
            if not color and "颜色" in name:
                color = value
            if not spec and any(word in name for word in ("套餐", "版本")):
                spec = value
        ram, storage = _find_ram_storage(sku_values, prop_names)
        url = f"https://{host}/item.htm?id={item_id}&skuId={sku_id}" if item_id else ""
        seen.add(sku_id)
        variants.append(
            TaobaoSkuVariant(
                color=color,
                spec=spec,
                sku_id=sku_id,
                url=url,
                ram_gb=ram,
                storage_gb=storage,
            )
        )
    return variants


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


def _sku_price_cents(value: dict) -> int | None:
    # Tmall's priceMoney is already in fen. priceText is displayed in yuan.
    # Parsing priceMoney with parse_price_cents multiplies cheap items by 100.
    raw_money = str(value.get("priceMoney") or "").strip()
    if re.fullmatch(r"\d+", raw_money):
        money_cents = int(raw_money)
        if 100 <= money_cents <= 10_000_000:
            return money_cents
    return parse_price_cents(str(value.get("priceText") or ""))


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
    price_cents = _sku_price_cents(price)
    sub_price = entry.get("subPrice") if isinstance(entry.get("subPrice"), dict) else {}
    sub_price_cents = _sku_price_cents(sub_price)
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
        if page_price is not None and page_price > estimated_from_label:
            coupon_total = page_price - estimated_from_label
        elif page_price is None:
            page_price = estimated_from_label
        # An explicit final-price label already reflects the platform's
        # applicable discounts. Nearby coupon text may overlap or describe
        # alternatives, so only the observed price difference is applied.
        breakdown = [{
            "type": "页面已含优惠",
            "raw": "页面补贴后价/券后价",
            "amount_cents": coupon_total,
            "applied": True,
        }] if coupon_total else []
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
    visible_prices = {
        amount for value in prices
        if (amount := parse_price_cents(value)) is not None
    }
    if (
        selector_price is not None
        and page_price == selector_price
        and visible_prices == {selector_price}
        and original_from_label is None
        and not breakdown
        and coupon_total == 0
    ):
        page_confidence = "high"
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
