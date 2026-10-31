from __future__ import annotations

import asyncio
import random
import time

from app.adapters.jd.parser import SkuVariant
from app.adapters.registry import get_adapter
from app.core.models import Account
from app.core.product_query import parse_product_query
from app.core.store_registry import stores_for_query

_VARIANT_CACHE_TTL_SECONDS = 1800
_variant_cache: dict[str, tuple[float, str, list[SkuVariant]]] = {}


async def search_model(query_text: str, account: Account) -> dict:
    query = parse_product_query(query_text)
    if not query.brand or not query.model:
        raise ValueError("请包含品牌和型号，例如 iQOO Neo11 至尊版 12G+512G")
    if query.ram_gb is None or query.storage_gb is None:
        raise ValueError("请包含内存和存储，例如 12G+512G")

    adapter = get_adapter("jd")
    if adapter is None:
        raise RuntimeError("京东适配器未注册")

    stores = stores_for_query(query.brand, query.model, query.variant)
    if not stores:
        raise ValueError("暂不支持该品牌的官方店")

    candidates: list[dict] = []
    for index, (store, model_url) in enumerate(stores):
        if index > 0:
            delay = random.uniform(20, 40)
            await asyncio.sleep(delay)

        if model_url is None:
            candidates.append(
                {
                    "store_name": store.name,
                    "store_type": store.store_type,
                    "model_url": None,
                    "title": None,
                    "requested_available": False,
                    "matched_sku_id": None,
                    "variants": [],
                    "error": "官方店暂未收录该型号",
                }
            )
            continue

        try:
            cached = _variant_cache.get(model_url)
            if cached is not None and time.monotonic() - cached[0] < _VARIANT_CACHE_TTL_SECONDS:
                title, variants = cached[1], cached[2]
            else:
                title, variants = await adapter.get_sku_variants(model_url, account)
                _variant_cache[model_url] = (time.monotonic(), title, variants)
        except Exception as exc:
            candidates.append(
                {
                    "store_name": store.name,
                    "store_type": store.store_type,
                    "model_url": model_url,
                    "title": None,
                    "requested_available": False,
                    "matched_sku_id": None,
                    "variants": [],
                    "error": str(exc),
                }
            )
            continue

        standard = [item for item in variants if item.spec == "官方标配"]
        if not standard:
            standard = [item for item in variants if "官方标配" in item.spec]
        if not standard:
            standard = variants

        by_spec: dict[tuple[int, int], SkuVariant] = {}
        for item in standard:
            if item.ram_gb is None or item.storage_gb is None:
                continue
            by_spec.setdefault((item.ram_gb, item.storage_gb), item)

        variant_options = [
            item
            for _, item in sorted(
                by_spec.items(),
                key=lambda pair: (pair[0][0], pair[0][1]),
            )
        ]
        matched = next(
            (
                item
                for item in variant_options
                if item.ram_gb == query.ram_gb and item.storage_gb == query.storage_gb
            ),
            None,
        )

        candidates.append(
            {
                "store_name": store.name,
                "store_type": store.store_type,
                "model_url": model_url,
                "title": title,
                "requested_available": matched is not None,
                "matched_sku_id": matched.sku_id if matched else None,
                "variants": [
                    {
                        "ram_gb": item.ram_gb,
                        "storage_gb": item.storage_gb,
                        "color": item.color,
                        "spec": item.spec,
                        "sku_id": item.sku_id,
                        "url": item.url,
                    }
                    for item in variant_options
                ],
                "error": None,
            }
        )

    return {
        "query": {
            "brand": query.brand,
            "model": query.model,
            "variant": query.variant,
            "ram_gb": query.ram_gb,
            "storage_gb": query.storage_gb,
        },
        "candidates": candidates,
    }
