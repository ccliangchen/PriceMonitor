from __future__ import annotations

import asyncio
import random
import re
import time
from dataclasses import dataclass

from app.adapters.jd.parser import SkuVariant
from app.adapters.registry import get_adapter
from app.adapters.taobao.parser import TaobaoSkuVariant
from app.core.exceptions import CaptchaRequired, LoginRequired, ParseError
from app.core.models import Account
from app.core.product_query import ProductQuery, parse_product_query
from app.core.shop_policy import ShopDecision, evaluate_shop
from app.core.store_registry import stores_for_query

_VARIANT_CACHE_TTL_SECONDS = 1800
_variant_cache: dict[str, tuple[float, str, list[SearchSku]]] = {}
_TAOBAO_MAX_ITEMS = 2


@dataclass(frozen=True)
class SearchSku:
    color: str
    spec: str
    sku_id: str
    url: str
    ram_gb: int | None
    storage_gb: int | None


def _from_jd(variant: SkuVariant) -> SearchSku:
    return SearchSku(
        color=variant.color,
        spec=variant.spec,
        sku_id=variant.sku_id,
        url=variant.url,
        ram_gb=variant.ram_gb,
        storage_gb=variant.storage_gb,
    )


def _from_taobao(variant: TaobaoSkuVariant) -> SearchSku:
    return SearchSku(
        color=variant.color,
        spec=variant.spec,
        sku_id=variant.sku_id,
        url=variant.url,
        ram_gb=variant.ram_gb,
        storage_gb=variant.storage_gb,
    )


def _sku_options(variants: list[SearchSku]) -> list[SearchSku]:
    standard = [item for item in variants if item.spec == "官方标配"]
    if not standard:
        standard = [item for item in variants if "官方标配" in item.spec]
    if not standard:
        standard = variants

    by_spec: dict[tuple[int, int], SearchSku] = {}
    for item in standard:
        if item.ram_gb is None or item.storage_gb is None:
            continue
        by_spec.setdefault((item.ram_gb, item.storage_gb), item)
    return [item for _, item in sorted(by_spec.items(), key=lambda pair: pair[0])]


def _matched_sku(options: list[SearchSku], query: ProductQuery) -> SearchSku | None:
    return next(
        (
            item
            for item in options
            if item.ram_gb == query.ram_gb and item.storage_gb == query.storage_gb
        ),
        None,
    )


def _query_payload(query: ProductQuery) -> dict:
    return {
        "brand": query.brand,
        "model": query.model,
        "variant": query.variant,
        "ram_gb": query.ram_gb,
        "storage_gb": query.storage_gb,
    }


def _candidate(
    *,
    platform: str,
    store_name: str,
    store_type: str,
    model_url: str | None,
    title: str | None,
    options: list[SearchSku],
    matched: SearchSku | None,
    platform_item_id: str | None,
    shop_evidence: dict[str, str],
    error: str | None = None,
) -> dict:
    return {
        "platform": platform,
        "store_name": store_name,
        "store_type": store_type,
        "model_url": model_url,
        "title": title,
        "requested_available": matched is not None,
        "matched_sku_id": matched.sku_id if matched else None,
        "platform_item_id": platform_item_id,
        "shop_evidence": shop_evidence,
        "variants": [
            {
                "ram_gb": item.ram_gb,
                "storage_gb": item.storage_gb,
                "color": item.color,
                "spec": item.spec,
                "sku_id": item.sku_id,
                "url": item.url,
            }
            for item in options
        ],
        "error": error,
    }


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", "", value or "").lower()


def _taobao_title_matches(title: str, query: ProductQuery) -> bool:
    normalized = _normalize_text(title)
    if not normalized:
        return False
    model = _normalize_text(query.model)
    variant = _normalize_text(query.variant)
    if model and model not in normalized:
        return False
    return not variant or variant in normalized


async def search_model(
    query_text: str,
    platform: str,
    account: Account,
) -> dict:
    query = parse_product_query(query_text)
    if not query.brand or not query.model:
        raise ValueError("请包含品牌和型号，例如 iQOO Neo11 至尊版 12G+512G")
    if query.ram_gb is None or query.storage_gb is None:
        raise ValueError("请包含内存和存储，例如 12G+512G")
    if platform == "jd":
        candidates = await _search_jd(query, account)
    elif platform == "taobao":
        candidates = await _search_taobao(query, account)
    else:
        raise ValueError("只支持京东或淘宝/天猫官方店搜索")

    return {"query": _query_payload(query), "candidates": candidates}


async def _search_jd(query: ProductQuery, account: Account) -> list[dict]:
    adapter = get_adapter("jd")
    if adapter is None:
        raise RuntimeError("京东适配器未注册")

    stores = stores_for_query(query.brand, query.model, query.variant)
    if not stores:
        raise ValueError("暂不支持该品牌的京东官方店")

    candidates: list[dict] = []
    for index, (store, model_url) in enumerate(stores):
        if index > 0:
            await asyncio.sleep(random.uniform(20, 40))

        if model_url is None:
            candidates.append(
                _candidate(
                    platform="jd",
                    store_name=store.name,
                    store_type=store.store_type,
                    model_url=None,
                    title=None,
                    options=[],
                    matched=None,
                    platform_item_id=None,
                    shop_evidence={},
                    error="官方店暂未收录该型号",
                )
            )
            continue

        try:
            cached = _variant_cache.get(model_url)
            if cached is not None and time.monotonic() - cached[0] < _VARIANT_CACHE_TTL_SECONDS:
                title, options = cached[1], cached[2]
            else:
                title, raw_variants = await adapter.get_sku_variants(model_url, account)
                options = _sku_options([_from_jd(item) for item in raw_variants])
                _variant_cache[model_url] = (time.monotonic(), title, options)
        except Exception as exc:
            candidates.append(
                _candidate(
                    platform="jd",
                    store_name=store.name,
                    store_type=store.store_type,
                    model_url=model_url,
                    title=None,
                    options=[],
                    matched=None,
                    platform_item_id=None,
                    shop_evidence={},
                    error=str(exc),
                )
            )
            continue

        matched = _matched_sku(options, query)
        evidence = (
            {
                "self_operated": "true",
                "brand_match": "true",
                "shop_brand": query.brand,
            }
            if store.store_type == "jd_official_self"
            else {
                "official_badge": "true",
                "badge_text": "官方旗舰店",
                "brand_match": "true",
                "shop_brand": query.brand,
            }
        )
        candidates.append(
            _candidate(
                platform="jd",
                store_name=store.name,
                store_type=store.store_type,
                model_url=model_url,
                title=title,
                options=options,
                matched=matched,
                platform_item_id=matched.sku_id if matched else None,
                shop_evidence=evidence,
            )
        )
    return candidates


async def _search_taobao(query: ProductQuery, account: Account) -> list[dict]:
    adapter = get_adapter("taobao")
    if adapter is None:
        raise RuntimeError("淘宝适配器未注册")

    find_store = getattr(adapter, "find_official_store", None)
    search_items = getattr(adapter, "search_store_items", None)
    resolve_with_skus = getattr(adapter, "resolve_listing_with_skus", None)
    if find_store is None or search_items is None or resolve_with_skus is None:
        raise RuntimeError("淘宝适配器不支持按型号搜索")

    keyword = " ".join(item for item in (query.model, query.variant) if item)
    store = await find_store(query.brand, account, keyword)
    if store is None:
        raise ValueError(f"没有找到{query.brand}的天猫官方旗舰店")

    store_error: Exception | None = None
    try:
        items = await search_items(store, keyword, account)
    except (CaptchaRequired, LoginRequired, ParseError) as exc:
        # The in-store search page is more aggressively protected than the
        # shop search card. If it is blocked, fall back to the sample items
        # already embedded in the shop search result, then let the item page
        # decide whether the account is actually usable.
        store_error = exc
        items = list(store.sample_items)
    if not items:
        items = list(store.sample_items)
    if not items and store_error is not None:
        raise store_error

    matched_items = [item for item in items if _taobao_title_matches(item.title, query)]
    if not matched_items:
        matched_items = [
            item for item in store.sample_items if _taobao_title_matches(item.title, query)
        ]
    if not matched_items:
        raise ValueError(
            f"{store.name}没有找到 {query.model} {query.variant} 的匹配商品，"
            "请检查型号或改用粘贴链接"
        )

    candidates: list[dict] = []
    for index, item in enumerate(matched_items[:_TAOBAO_MAX_ITEMS]):
        if index > 0:
            await asyncio.sleep(random.uniform(3, 6))
        try:
            info, raw_variants = await resolve_with_skus(item.url, account)
        except Exception as exc:
            candidates.append(
                _candidate(
                    platform="taobao",
                    store_name=store.name,
                    store_type="official_flagship",
                    model_url=item.url,
                    title=item.title,
                    options=[],
                    matched=None,
                    platform_item_id=item.item_id,
                    shop_evidence={},
                    error=str(exc),
                )
            )
            continue

        decision = evaluate_shop(info, query.brand)
        if decision.decision != ShopDecision.ALLOWED:
            candidates.append(
                _candidate(
                    platform="taobao",
                    store_name=info.shop_name or store.name,
                    store_type=info.shop_type,
                    model_url=item.url,
                    title=info.title or item.title,
                    options=[],
                    matched=None,
                    platform_item_id=info.platform_item_id,
                    shop_evidence=info.evidence,
                    error=decision.reason,
                )
            )
            continue

        options = _sku_options([_from_taobao(variant) for variant in raw_variants])
        matched = _matched_sku(options, query)
        candidates.append(
            _candidate(
                platform="taobao",
                store_name=info.shop_name or store.name,
                store_type=info.shop_type,
                model_url=info.url,
                title=info.title or item.title,
                options=options,
                matched=matched,
                platform_item_id=info.platform_item_id,
                shop_evidence=info.evidence,
                error=None if options else "商品页没有读到可用 SKU 规格",
            )
        )
    return candidates
