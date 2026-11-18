from dataclasses import dataclass
from enum import StrEnum

from app.adapters.base import ListingInfo


class ShopDecision(StrEnum):
    ALLOWED = "allowed"
    REJECTED = "rejected"
    NEEDS_REVIEW = "needs_review"


@dataclass(frozen=True)
class ShopPolicyResult:
    decision: ShopDecision
    reason: str


BRAND_KEYWORDS: dict[str, tuple[str, ...]] = {
    "apple": ("apple", "苹果", "iphone", "ipad", "macbook"),
    "苹果": ("apple", "苹果", "iphone", "ipad", "macbook"),
    "huawei": ("huawei", "华为"),
    "华为": ("huawei", "华为"),
    "xiaomi": ("xiaomi", "小米", "redmi", "红米"),
    "小米": ("xiaomi", "小米", "redmi", "红米"),
    "honor": ("honor", "荣耀"),
    "荣耀": ("honor", "荣耀"),
    "iqoo": ("iqoo",),
    "vivo": ("vivo",),
    "oppo": ("oppo",),
    "oneplus": ("oneplus", "一加"),
    "一加": ("oneplus", "一加"),
    "samsung": ("samsung", "三星", "galaxy"),
    "三星": ("samsung", "三星", "galaxy"),
    "realme": ("realme", "真我"),
    "真我": ("realme", "真我"),
    "meizu": ("meizu", "魅族"),
    "魅族": ("meizu", "魅族"),
}


def _normalize_brand(value: str) -> str:
    return "".join(value.lower().split())


def brand_matches(product_brand: str, haystack: str) -> bool:
    brand = _normalize_brand(product_brand)
    normalized = _normalize_brand(haystack)
    if not brand:
        return False
    if brand in normalized:
        return True
    keywords = BRAND_KEYWORDS.get(brand, ())
    return any(_normalize_brand(keyword) in normalized for keyword in keywords)


def shop_brand_matches(product_brand: str, shop_name: str) -> bool:
    """Allow a documented parent brand in an official shop name only.

    Product-title matching stays strict, so a vivo phone cannot match an
    iQOO model query merely through this shop-name relationship.
    """
    if brand_matches(product_brand, shop_name):
        return True
    return _normalize_brand(product_brand) == "iqoo" and "vivo" in _normalize_brand(shop_name)


def evaluate_shop(info: ListingInfo, product_brand: str) -> ShopPolicyResult:
    """Any recognized JD, Taobao or Tmall item may be monitored."""
    del product_brand
    if info.platform not in ("jd", "taobao") or not info.platform_item_id:
        return ShopPolicyResult(ShopDecision.REJECTED, "不是受支持的商品详情页")
    return ShopPolicyResult(ShopDecision.ALLOWED, "商品链接可监测")
