from __future__ import annotations

import re
from dataclasses import dataclass, field

BRAND_ALIASES: dict[str, str] = {
    "iqoo": "iQOO",
    "vivo": "vivo",
    "小米": "小米",
    "xiaomi": "小米",
    "红米": "Redmi",
    "redmi": "Redmi",
    "华为": "华为",
    "huawei": "华为",
    "荣耀": "荣耀",
    "honor": "荣耀",
    "苹果": "Apple",
    "apple": "Apple",
    "oppo": "OPPO",
    "一加": "一加",
    "oneplus": "一加",
    "三星": "三星",
    "samsung": "三星",
    "真我": "realme",
    "realme": "realme",
    "魅族": "魅族",
    "meizu": "魅族",
}

VARIANT_WORDS = (
    "至尊版",
    "竞速版",
    "活力版",
    "青春版",
    "标准版",
    "Pro",
    "Ultra",
    "Max",
    "Plus",
    "Air",
    "Fold",
    "Flip",
)

SPEC_PLUS_RE = re.compile(
    r"(\d{1,3})\s*(?:GB|G)?\s*[\+＋]\s*(\d{2,4})\s*(?:GB|G)?",
    re.IGNORECASE,
)
SPEC_SPACE_RE = re.compile(
    r"(\d{1,3})\s*(?:GB|G)\s+(\d{2,4})\s*(?:GB|G)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ProductQuery:
    raw: str
    brand: str
    model: str
    variant: str
    ram_gb: int | None
    storage_gb: int | None
    color: str | None = None
    keywords: list[str] = field(default_factory=list)


def _strip_specs(text: str) -> tuple[str, int | None, int | None]:
    for pattern in (SPEC_PLUS_RE, SPEC_SPACE_RE):
        match = pattern.search(text)
        if match:
            ram = int(match.group(1))
            storage = int(match.group(2))
            return f"{text[:match.start()]} {text[match.end():]}", ram, storage
    return text, None, None


def _find_brand(text: str) -> tuple[str, str]:
    lowered = text.lower()
    for alias in sorted(BRAND_ALIASES, key=len, reverse=True):
        if alias in lowered:
            index = lowered.index(alias)
            canonical = BRAND_ALIASES[alias]
            remaining = f"{text[:index]} {text[index + len(alias):]}"
            return canonical, remaining
    return "", text


def _find_variant(text: str) -> tuple[str, str]:
    lowered = text.lower()
    for variant in sorted(VARIANT_WORDS, key=len, reverse=True):
        index = lowered.find(variant.lower())
        if index >= 0:
            remaining = f"{text[:index]} {text[index + len(variant):]}"
            return variant, remaining
    return "", text


def _clean_model(text: str) -> str:
    cleaned = re.sub(r"[\s,，。;；:：/\\|()（）【】\[\]{}<>《》\"'“”‘’]+", " ", text)
    cleaned = " ".join(cleaned.split()).strip()
    if not cleaned:
        return ""
    # "neo11" -> "Neo11", keep "iPhone 17" readable
    parts = []
    for part in cleaned.split(" "):
        if part and part[0].islower():
            part = part[0].upper() + part[1:]
        parts.append(part)
    return " ".join(parts)


def parse_product_query(text: str) -> ProductQuery:
    raw = text.strip()
    without_specs, ram, storage = _strip_specs(raw)
    brand, without_brand = _find_brand(without_specs)
    variant, without_variant = _find_variant(without_brand)
    model = _clean_model(without_variant)

    keywords = [value.lower() for value in (brand, model, variant) if value]
    if ram is not None:
        keywords.append(str(ram))
    if storage is not None:
        keywords.append(str(storage))

    return ProductQuery(
        raw=raw,
        brand=brand,
        model=model,
        variant=variant,
        ram_gb=ram,
        storage_gb=storage,
        keywords=keywords,
    )
