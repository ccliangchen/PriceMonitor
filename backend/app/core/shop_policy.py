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


ALLOWED_SHOP_TYPES = {"official_flagship", "jd_official_self"}

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


def evaluate_shop(info: ListingInfo, product_brand: str) -> ShopPolicyResult:
    """Apply the official-store admission policy.

    Adapters only collect evidence; this function is the single place that
    decides whether a listing may be monitored.
    """
    if info.shop_type == "unknown":
        return ShopPolicyResult(ShopDecision.NEEDS_REVIEW, "店铺类型无法确认")
    if info.shop_type not in ALLOWED_SHOP_TYPES:
        return ShopPolicyResult(ShopDecision.REJECTED, "不是官方旗舰店/官方自营")

    if (
        info.shop_type == "official_flagship"
        and str(info.evidence.get("official_badge", "")).lower() != "true"
    ):
        return ShopPolicyResult(ShopDecision.NEEDS_REVIEW, "缺少官方旗舰店标识证据")
    if (
        info.shop_type == "jd_official_self"
        and str(info.evidence.get("self_operated", "")).lower() != "true"
    ):
        return ShopPolicyResult(ShopDecision.NEEDS_REVIEW, "缺少京东自营标识证据")

    brand_value = str(info.evidence.get("brand_match", "")).lower()
    if brand_value == "false":
        return ShopPolicyResult(ShopDecision.REJECTED, "店铺品牌与商品品牌不一致")
    if brand_value != "true":
        haystack = _normalize_brand(
            f"{info.title} {info.shop_name} {info.evidence.get('shop_brand', '')}"
        )
        if not brand_matches(product_brand, haystack):
            return ShopPolicyResult(ShopDecision.NEEDS_REVIEW, "未在标题/店铺名中确认品牌一致")

    shop_brand = str(info.evidence.get("shop_brand", "")).strip()
    if shop_brand and _normalize_brand(shop_brand) != _normalize_brand(product_brand):
        return ShopPolicyResult(ShopDecision.REJECTED, "店铺品牌与商品品牌不一致")

    return ShopPolicyResult(ShopDecision.ALLOWED, "官方店铺且品牌一致")
