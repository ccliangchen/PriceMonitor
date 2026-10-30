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


def _normalize_brand(value: str) -> str:
    return "".join(value.lower().split())


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

    brand_match = str(info.evidence.get("brand_match", "")).lower()
    if brand_match == "false":
        return ShopPolicyResult(ShopDecision.REJECTED, "店铺品牌与商品品牌不一致")
    if brand_match != "true":
        return ShopPolicyResult(ShopDecision.NEEDS_REVIEW, "品牌一致性未确认")

    shop_brand = str(info.evidence.get("shop_brand", "")).strip()
    if shop_brand and _normalize_brand(shop_brand) != _normalize_brand(product_brand):
        return ShopPolicyResult(ShopDecision.REJECTED, "店铺品牌与商品品牌不一致")

    return ShopPolicyResult(ShopDecision.ALLOWED, "官方店铺且品牌一致")
