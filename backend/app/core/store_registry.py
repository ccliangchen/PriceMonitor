from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class JdStore:
    brand: str
    store_type: str
    name: str
    shop_id: str
    vender_id: str
    index_url: str
    model_urls: dict[str, str] = field(default_factory=dict)


JD_STORES: tuple[JdStore, ...] = (
    JdStore(
        brand="iQOO",
        store_type="jd_official_self",
        name="iQOO京东自营旗舰店",
        shop_id="1000310642",
        vender_id="1000310642",
        index_url="https://mall.jd.com/index-1000310642.html",
        model_urls={
            "neo12": "https://item.jd.com/100327252953.html",
            "neo11至尊版": "https://item.jd.com/100396381212.html",
            "neo11": "https://item.jd.com/100284826948.html",
        },
    ),
    JdStore(
        brand="iQOO",
        store_type="official_flagship",
        name="iQOO官方旗舰店",
        shop_id="10175519",
        vender_id="10314962",
        index_url="https://mall.jd.com/index-10175519.html",
        model_urls={
            "neo12": "https://item.jd.com/10237128678205.html",
        },
    ),
)


def normalize_model_key(model: str, variant: str) -> str:
    return f"{model}{variant}".replace(" ", "").lower()


def stores_for_query(brand: str, model: str, variant: str) -> list[tuple[JdStore, str | None]]:
    brand_key = brand.strip().lower()
    key = normalize_model_key(model, variant)
    model_key = model.replace(" ", "").lower()
    result: list[tuple[JdStore, str | None]] = []
    for store in JD_STORES:
        if store.brand.lower() != brand_key:
            continue
        url = store.model_urls.get(key) or store.model_urls.get(model_key)
        result.append((store, url))
    return result
