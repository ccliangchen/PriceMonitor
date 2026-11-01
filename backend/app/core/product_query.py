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
BRAND_PRIORITY = (
    "iqoo",
    "redmi",
    "oneplus",
    "realme",
    "honor",
    "huawei",
    "xiaomi",
    "vivo",
    "oppo",
    "samsung",
    "meizu",
    "apple",
)
MODEL_PATTERNS = (
    r"\b(iPhone\s?\d+)",
    r"\b(Galaxy\s?[A-Z]\d+[A-Za-z]*)",
    r"\b(Neo\s?\d+[A-Za-z]*)",
    r"\b(Reno\s?\d+[A-Za-z]*)",
    r"\b(Find\s?X\d*[A-Za-z]*)",
    r"\b(Mate\s?\d+[A-Za-z]*)",
    r"\b(Pura\s?\d+[A-Za-z]*)",
    r"\b(nova\s?\d+[A-Za-z]*)",
    r"\b(Magic\s?\d+[A-Za-z]*)",
    r"\b(Redmi\s?[A-Z]?\d+[A-Za-z]*)",
    r"\b(K\d{2}[A-Za-z]*)",
    r"\b(X\d{2,4}[A-Za-z]*)",
    r"(?:小米|Redmi)\s?(\d{1,3}[A-Za-z]*)",
    r"(?:一加|OnePlus)\s?(\d{1,3}[A-Za-z]*)",
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


def suggest_fields_from_title(title: str) -> dict[str, str]:
    """Best-effort brand/model/variant suggestions for a product title.

    These values only prefill the add-product form; the user can edit them.
    """
    lowered = (title or "").lower()
    brand = ""
    for alias in BRAND_PRIORITY:
        if alias in lowered:
            brand = BRAND_ALIASES[alias]
            break

    model = ""
    for pattern in MODEL_PATTERNS:
        match = re.search(pattern, title or "", re.IGNORECASE)
        if match:
            model = re.sub(r"\s+", " ", match.group(1)).strip()
            break

    variant = ""
    for word in sorted(VARIANT_WORDS, key=len, reverse=True):
        for match in re.finditer(re.escape(word), title or "", re.IGNORECASE):
            prefix = (title or "")[max(0, match.start() - 4) : match.start()]
            # "骁龙8至尊版" is a chipset, not a product variant.
            if any(token in prefix for token in ("骁龙", "芯片", "处理器", "平台")):
                continue
            variant = word
            break
        if variant:
            break

    return {"brand": brand, "model": model, "variant": variant}


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
