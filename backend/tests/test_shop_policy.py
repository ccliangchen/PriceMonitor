from app.adapters.base import ListingInfo
from app.core.shop_policy import ShopDecision, evaluate_shop


def make_info(
    shop_type: str,
    *,
    title: str = "iQOO Neo11 至尊版 12GB+512GB",
    shop_name: str = "iQOO官方旗舰店",
    **evidence: str,
) -> ListingInfo:
    return ListingInfo(
        platform="jd",
        url="https://item.jd.com/100.html",
        title=title,
        shop_name=shop_name,
        shop_type=shop_type,
        platform_item_id="100",
        evidence=evidence,
    )


def test_official_flagship_allowed():
    result = evaluate_shop(
        make_info(
            "official_flagship",
            official_badge="true",
            brand_match="true",
            shop_brand="iQOO",
        ),
        "iQOO",
    )

    assert result.decision == ShopDecision.ALLOWED


def test_flagship_without_official_badge_needs_review():
    result = evaluate_shop(
        make_info("official_flagship", brand_match="true"),
        "iQOO",
    )

    assert result.decision == ShopDecision.NEEDS_REVIEW


def test_unknown_shop_needs_review():
    result = evaluate_shop(make_info("unknown"), "iQOO")

    assert result.decision == ShopDecision.NEEDS_REVIEW


def test_other_shop_rejected():
    result = evaluate_shop(
        make_info("other", official_badge="true", brand_match="true"),
        "iQOO",
    )

    assert result.decision == ShopDecision.REJECTED


def test_brand_mismatch_rejected():
    result = evaluate_shop(
        make_info("official_flagship", official_badge="true", brand_match="false"),
        "iQOO",
    )

    assert result.decision == ShopDecision.REJECTED


def test_jd_official_self_allowed():
    result = evaluate_shop(
        make_info(
            "jd_official_self",
            self_operated="true",
            brand_match="true",
            shop_brand="iQOO",
        ),
        "iQOO",
    )

    assert result.decision == ShopDecision.ALLOWED


def test_jd_official_self_without_badge_needs_review():
    result = evaluate_shop(
        make_info("jd_official_self", brand_match="true"),
        "iQOO",
    )

    assert result.decision == ShopDecision.NEEDS_REVIEW


def test_brand_match_falls_back_to_title():
    result = evaluate_shop(
        make_info(
            "official_flagship",
            official_badge="true",
        ),
        "iQOO",
    )

    assert result.decision == ShopDecision.ALLOWED


def test_apple_alias_matches_iphone_title():
    result = evaluate_shop(
        make_info(
            "jd_official_self",
            title="Apple iPhone 17 Pro 256GB",
            shop_name="京东自营",
            self_operated="true",
        ),
        "Apple",
    )

    assert result.decision == ShopDecision.ALLOWED


def test_unmatched_brand_needs_review():
    result = evaluate_shop(
        make_info(
            "official_flagship",
            title="vivo X200 12GB+256GB",
            shop_name="vivo官方旗舰店",
            official_badge="true",
        ),
        "iQOO",
    )

    assert result.decision == ShopDecision.NEEDS_REVIEW


def test_shop_brand_mismatch_rejected():
    result = evaluate_shop(
        make_info(
            "official_flagship",
            official_badge="true",
            brand_match="true",
            shop_brand="vivo",
        ),
        "iQOO",
    )

    assert result.decision == ShopDecision.REJECTED
