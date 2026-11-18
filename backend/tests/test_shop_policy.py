from app.adapters.base import ListingInfo
from app.core.shop_policy import ShopDecision, evaluate_shop


def make_info(shop_type: str, platform: str = "jd", item_id: str = "100") -> ListingInfo:
    return ListingInfo(
        platform=platform,
        url="https://item.jd.com/100.html",
        title="普通商品",
        shop_name="普通店铺",
        shop_type=shop_type,
        platform_item_id=item_id,
    )


def test_all_shop_types_and_categories_are_allowed():
    for shop_type in ("official_flagship", "jd_official_self", "other", "unknown"):
        assert evaluate_shop(make_info(shop_type), "").decision == ShopDecision.ALLOWED


def test_brand_mismatch_does_not_reject_user_selected_link():
    assert evaluate_shop(make_info("other"), "不相干品牌").decision == ShopDecision.ALLOWED


def test_only_supported_item_links_are_allowed():
    assert evaluate_shop(make_info("other", platform="other"), "").decision == ShopDecision.REJECTED
    assert evaluate_shop(make_info("other", item_id=""), "").decision == ShopDecision.REJECTED
