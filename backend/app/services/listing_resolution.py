from __future__ import annotations

from urllib.parse import urlparse

from app.adapters.base import ListingInfo
from app.adapters.jd.adapter import JdAdapter, clean_title
from app.adapters.jd.adapter import normalize_url as normalize_jd_url
from app.adapters.jd.adapter import parse_specs as parse_jd_specs
from app.adapters.jd.parser import extract_embedded_price_cents as jd_embedded_price
from app.adapters.jd.parser import extract_sku
from app.adapters.jd.parser import parse_product_page as parse_jd_page
from app.adapters.taobao.adapter import TaobaoAdapter
from app.adapters.taobao.adapter import _listing_target as taobao_listing_target
from app.adapters.taobao.adapter import parse_specs as parse_taobao_specs
from app.adapters.taobao.parser import (
    DEGRADED_PAGE_PHRASES,
    GENERIC_TITLES,
    choose_title,
    extract_embedded_shop_name,
    extract_item_id,
    extract_sku_id,
)
from app.adapters.taobao.parser import (
    extract_embedded_price_cents as taobao_embedded_price,
)
from app.adapters.taobao.parser import (
    parse_product_page as parse_taobao_page,
)
from app.core.exceptions import CaptchaRequired, LoginRequired, ParseError
from app.core.product_query import suggest_fields_from_title
from app.services.edge_bridge import edge_bridge


async def resolve_with_browser_extension(platform: str, url: str) -> ListingInfo:
    """Read link metadata in the user's selected, already signed-in browser."""
    if platform == "jd":
        target = normalize_jd_url(url)
        requested_id = extract_sku(target)
        visit_url = f"https://item.jd.com/{requested_id}.html" if requested_id else target
        observation = await edge_bridge.observe("jd", visit_url)
        final_url = str(observation.get("url") or "")
        JdAdapter._assert_not_blocked(
            final_url, str(observation.get("title") or ""), str(observation.get("body") or "")
        )
        if urlparse(final_url).hostname not in ("item.jd.com", "item.m.jd.com"):
            raise ParseError("京东页面不是商品详情页，本次链接未添加")
        item_id = extract_sku(final_url)
        if not item_id or (requested_id and item_id != requested_id):
            raise ParseError("京东页面跳转到其他商品，本次链接未添加")
        body = str(observation.get("body") or "")
        if len(body.strip()) < 40:
            raise ParseError("京东商品页未完整加载，暂时无法读取链接信息")
        title = clean_title(str(observation.get("title") or ""))
        if title in ("京东商城", "京东验证"):
            for candidate in observation.get("title_texts") or []:
                candidate_title = clean_title(str(candidate))
                if len(candidate_title) > 4 and candidate_title not in ("京东商城", "京东验证"):
                    title = candidate_title
                    break
        if not title or title in ("京东商城", "京东验证"):
            raise ParseError("京东商品页没有可识别的商品标题")
        parsed = parse_jd_page(
            url=final_url,
            title=title,
            body_text=body,
            price_texts=observation.get("price_texts") or [],
            shop_texts=observation.get("shop_texts") or [],
            embedded_price_cents=jd_embedded_price(str(observation.get("html") or "")),
        )
        if parsed.status == "captcha":
            raise CaptchaRequired(parsed.error or "京东页面需要验证")
        if parsed.status == "login_required":
            raise LoginRequired(parsed.error or "京东页面需要登录")
        specs = parse_jd_specs(title)
        specs.update({key: value for key, value in suggest_fields_from_title(title).items() if value})
        return ListingInfo(
            platform="jd", url=f"https://item.m.jd.com/product/{item_id}.html",
            title=title, shop_name=parsed.shop_name, shop_type=parsed.shop_type,
            platform_item_id=item_id, detected_specs=specs, evidence=parsed.evidence,
        )

    if platform != "taobao":
        raise ParseError("不支持的商品平台")
    target = taobao_listing_target(url)
    requested_id = extract_item_id(target)
    observation = await edge_bridge.observe("taobao", target, extract_sku_id(target))
    final_url = str(observation.get("url") or "")
    body = str(observation.get("body") or "")
    title = choose_title(
        str(observation.get("title") or ""), observation.get("title_texts") or []
    )
    TaobaoAdapter._assert_not_blocked(final_url, title, body)
    item_id = extract_item_id(final_url)
    if not item_id or (requested_id and item_id != requested_id):
        raise ParseError("淘宝页面跳转到其他商品，本次链接未添加")
    if urlparse(final_url).hostname not in ("item.taobao.com", "detail.tmall.com"):
        raise ParseError("淘宝页面不是商品详情页，本次链接未添加")
    if len(body.strip()) < 40 or title in GENERIC_TITLES or not title:
        raise ParseError("淘宝商品页未完整加载，暂时无法读取链接信息")
    if any(phrase in body or phrase in title for phrase in DEGRADED_PAGE_PHRASES):
        raise ParseError("淘宝商品页处于访问异常状态，本次链接信息未采纳")
    html = str(observation.get("html") or "")
    shop_texts = list(observation.get("shop_texts") or [])
    embedded_shop = extract_embedded_shop_name(html)
    if embedded_shop:
        shop_texts.insert(0, embedded_shop)
    parsed = parse_taobao_page(
        url=final_url, title=title, body_text=body,
        price_texts=observation.get("price_texts") or [], shop_texts=shop_texts,
        embedded_price_cents=taobao_embedded_price(html),
    )
    if parsed.status == "captcha":
        raise CaptchaRequired(parsed.error or "淘宝页面需要验证")
    if parsed.status == "login_required":
        raise LoginRequired(parsed.error or "淘宝页面需要登录")
    specs = parse_taobao_specs(title)
    specs.update({key: value for key, value in suggest_fields_from_title(title).items() if value})
    return ListingInfo(
        platform="taobao", url=target, title=title,
        shop_name=parsed.shop_name, shop_type=parsed.shop_type,
        platform_item_id=item_id,
        platform_sku_id=extract_sku_id(target) or extract_sku_id(final_url),
        detected_specs=specs, evidence=parsed.evidence,
    )
