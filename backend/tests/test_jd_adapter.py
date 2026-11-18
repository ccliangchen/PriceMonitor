import pytest

from app.adapters.jd.adapter import (
    JdAdapter,
    _click_exact_text,
    clean_title,
    has_login_cookies,
    normalize_url,
    parse_specs,
    prefer_mobile_url,
)
from app.core.exceptions import ParseError, RateLimited
from app.core.models import Account, Listing


def test_has_login_cookies_supports_current_jd_cookies():
    assert has_login_cookies({"thor", "pin"})
    assert has_login_cookies({"thor", "unick"})
    assert has_login_cookies({"pt_key", "pt_pin"})
    assert not has_login_cookies({"pin"})
    assert not has_login_cookies({"thor"})
    assert not has_login_cookies(set())


def test_normalize_url_accepts_jd_hosts():
    assert normalize_url("item.jd.com/100.html") == "https://item.jd.com/100.html"
    assert normalize_url("https://u.jd.com/abc") == "https://u.jd.com/abc"
    assert normalize_url("https://3.cn/abc") == "https://3.cn/abc"
    assert normalize_url("https://item.m.jd.com/product/100.html") == (
        "https://item.m.jd.com/product/100.html"
    )


def test_normalize_url_rejects_non_jd_hosts():
    with pytest.raises(ParseError):
        normalize_url("https://example.com/item.html")
    with pytest.raises(ParseError):
        normalize_url("")


def test_prefer_mobile_url():
    assert prefer_mobile_url("https://item.jd.com/10237128678205.html") == (
        "https://item.m.jd.com/product/10237128678205.html"
    )
    assert prefer_mobile_url("https://item.m.jd.com/product/10237128678205.html") == (
        "https://item.m.jd.com/product/10237128678205.html"
    )
    assert prefer_mobile_url("https://u.jd.com/abc") == "https://u.jd.com/abc"


def test_rate_limit_page_is_detected():
    with pytest.raises(RateLimited):
        JdAdapter._assert_not_blocked(  # noqa: SLF001
            "https://item.m.jd.com/product/1.html",
            "京东",
            "抱歉，访问频繁，请稍后再试",
        )


def test_pc_frequency_page_is_retryable():
    with pytest.raises(RateLimited):
        JdAdapter._assert_not_blocked(  # noqa: SLF001
            "https://cfe.jd.com/pc-frequent-pro?reason=403",
            "PC频控页",
            "暂时无法展示该商品的信息",
        )


def test_product_page_login_prompt_is_not_login_redirect():
    JdAdapter._assert_not_blocked(  # noqa: SLF001
        "https://item.jd.com/100.html",
        "iQOO 京东商品",
        "京东价 ￥3999.00 领券请登录 其他商品信息",
    )


def test_extension_observation_selects_verified_seller_from_page_candidates():
    adapter = JdAdapter(None)
    listing = Listing(
        id=2,
        url="https://item.jd.com/100.html",
        platform_item_id="100",
        shop_name="iQOO官方旗舰店",
        shop_type="official_flagship",
    )
    quote = adapter.quote_from_observation(
        listing,
        "https://item.jd.com/100.html",
        "iQOO Neo12",
        "京东价 ￥4899.00 iQOO官方旗舰店 猜你喜欢 某某京东自营旗舰店 评价 配送 参数 优惠 活动详情",
        ["￥4899.00"],
        ["某某京东自营旗舰店", "iQOO官方旗舰店"],
        [],
        "",
    )
    assert quote.status == "ok"
    assert quote.effective_price_cents == 489900
    assert quote.confidence == "high"


def test_subsidy_page_without_final_amount_is_not_treated_as_true_price():
    adapter = JdAdapter(None)
    listing = Listing(
        id=2,
        url="https://item.jd.com/100.html",
        platform_item_id="100",
        shop_name="iQOO官方旗舰店",
        shop_type="official_flagship",
    )
    quote = adapter.quote_from_observation(
        listing,
        "https://item.jd.com/100.html",
        "iQOO Neo12",
        "京东价 ￥4899.00 享受国补优惠，具体以结算为准 iQOO官方旗舰店 商品详情 评价 参数",
        ["￥4899.00"],
        ["iQOO官方旗舰店"],
        [],
        "",
    )
    assert quote.status == "ok"
    assert quote.confidence == "low"


def test_visible_applied_price_survives_page_with_higher_subsidy_label():
    adapter = JdAdapter(None)
    listing = Listing(
        id=1,
        url="https://item.jd.com/100.html",
        platform_item_id="100",
        shop_name="iQOO京东自营旗舰店",
        shop_type="jd_official_self",
    )
    quote = adapter.quote_from_observation(
        listing,
        "https://item.jd.com/100.html",
        "iQOO Neo11",
        "¥3193.48 国补领后价 ¥3699 已享受：限时立减5 国家补贴｜领后减￥500 可再享：最高返159京豆 iQOO京东自营旗舰店 商品详情 配送",
        ["¥3193.48", "¥3699"],
        [],
        [],
        "",
    )
    assert quote.status == "ok"
    assert quote.effective_price_cents == 319348
    assert quote.confidence == "high"


def test_real_edge_official_flagship_observation_keeps_primary_price():
    adapter = JdAdapter(None)
    listing = Listing(
        id=2,
        url="https://item.jd.com/10237128678205.html",
        platform_item_id="10237128678205",
        shop_name="iQOO官方旗舰店",
        shop_type="official_flagship",
    )
    quote = adapter.quote_from_observation(
        listing,
        "https://item.jd.com/10237128678205.html",
        "iQOO Neo12",
        "收藏 ¥3848.48 国补领后价 ¥4899 已享受：国家补贴｜领后减￥500 满4000减550 可再享：最高返192京豆 iQOO官方旗舰店 商品详情",
        ["¥3848.48", "¥4899"],
        [],
        [],
        "",
    )
    assert quote.effective_price_cents == 384848
    assert quote.confidence == "high"


def test_edge_ignores_recommended_product_price_outside_primary_region():
    adapter = JdAdapter(None)
    listing = Listing(
        id=6,
        url="https://item.jd.com/100305145887.html",
        platform_item_id="100305145887",
        shop_name="iQOO京东自营旗舰店",
        shop_type="jd_official_self",
    )
    quote = adapter.quote_from_observation(
        listing,
        "https://item.jd.com/100305145887.html",
        "iQOO Neo11 16GB+512GB",
        "猜你喜欢 到手价 ¥1949.46 直降600元 领后减¥500 领后减￥500 京东自营",
        ["¥1949.46"],
        ["iQOO京东自营旗舰店"],
        ["领后减￥500"],
        "",
        "¥3943.48 已享受：直降600元 领后减¥500 领后减￥500 iQOO京东自营旗舰店",
        ["￥3943.48"],
        require_primary=True,
    )
    assert quote.effective_price_cents == 394348
    assert quote.confidence == "high"
    assert [item["raw"] for item in quote.coupon_breakdown].count("领后减¥500") == 1
    assert not any(item["applied"] for item in quote.coupon_breakdown)


def test_edge_without_primary_region_cannot_trigger_new_low():
    adapter = JdAdapter(None)
    listing = Listing(
        id=6,
        url="https://item.jd.com/100305145887.html",
        platform_item_id="100305145887",
        shop_name="iQOO京东自营旗舰店",
        shop_type="jd_official_self",
    )
    quote = adapter.quote_from_observation(
        listing,
        "https://item.jd.com/100305145887.html",
        "iQOO Neo11 16GB+512GB",
        "猜你喜欢 到手价 ¥1949.46 京东自营 商品详情 配送 评价 更多推荐商品",
        ["¥1949.46"],
        ["iQOO京东自营旗舰店"],
        [],
        "",
        require_primary=True,
    )
    assert quote.confidence == "low"


def test_edge_title_anchor_uses_product_price_before_coupon_and_recommendations():
    adapter = JdAdapter(None)
    product_title = "vivoiQOO Neo11 至尊版 16GB+512GB乘风 2K护眼超冠屏 9100mAh蓝海大电池 天玑9500M电竞游戏学生手机"
    listing = Listing(
        id=6,
        url="https://item.jd.com/100305145887.html",
        platform_item_id="100305145887",
        title=product_title,
        shop_name="iQOO京东自营旗舰店",
        shop_type="jd_official_self",
    )
    body = (
        "领券中心 领后减￥500 "
        f"{product_title} 收藏 ¥3943.48 国补领后价 ¥4699 "
        "已享受：国家补贴｜领后减￥500 iQOO京东自营旗舰店 "
        "商品详情 猜你喜欢 到手价 ¥1949.46"
    )
    quote = adapter.quote_from_observation(
        listing,
        "https://item.jd.com/100305145887.html",
        product_title,
        body,
        ["￥500", "¥1949.46", "¥3943.48"],
        [],
        ["领后减￥500"],
        "",
        "国补领后价 ￥500 领后减￥500",
        ["￥500"],
        require_primary=True,
    )
    assert quote.effective_price_cents == 394348
    assert quote.confidence == "high"
    assert not any(item["applied"] for item in quote.coupon_breakdown)


def test_verified_jd_seller_survives_missing_current_shop_selector():
    adapter = JdAdapter(None)
    product_title = "vivoiQOO Neo11 至尊版 16GB+512GB乘风 2K护眼超冠屏 9100mAh蓝海大电池 天玑9500M电竞游戏学生手机"
    listing = Listing(
        id=6,
        url="https://item.jd.com/100305145887.html",
        platform_item_id="100305145887",
        title=product_title,
        shop_name="iQOO京东自营旗舰店",
        shop_type="jd_official_self",
        shop_verified=True,
    )
    body = f"{product_title} 收藏 ¥3948.48 国补领后价 ¥4699 已享受：领后减￥500 商品详情"
    quote = adapter.quote_from_observation(
        listing,
        "https://item.jd.com/100305145887.html",
        product_title,
        body,
        [],
        [],
        [],
        "",
        require_primary=True,
    )
    assert quote.effective_price_cents == 394848
    assert quote.confidence == "high"


def test_shop_change_does_not_block_price_capture():
    adapter = JdAdapter(None)
    product_title = "vivoiQOO Neo11 至尊版 16GB+512GB乘风 2K护眼超冠屏 9100mAh蓝海大电池 天玑9500M电竞游戏学生手机"
    listing = Listing(
        id=6,
        url="https://item.jd.com/100305145887.html",
        platform_item_id="100305145887",
        title=product_title,
        shop_name="iQOO京东自营旗舰店",
        shop_type="jd_official_self",
        shop_verified=True,
    )
    body = f"{product_title} 收藏 ¥3948.48 某某数码专营店 商品详情"
    quote = adapter.quote_from_observation(
            listing,
            "https://item.jd.com/100305145887.html",
            product_title,
            body,
            [],
            [],
            [],
            "",
            require_primary=True,
        )
    assert quote.status == "ok"
    assert quote.effective_price_cents == 394848
    assert listing.shop_name == "某某数码专营店"


def test_small_coupon_like_amount_falls_back_to_main_jd_price():
    title = "一加手机旗舰新品高性能大电池高清屏幕长续航正品现货全国包邮智能手机"
    listing = Listing(
        id=9, url="https://item.jd.com/123456789.html",
        platform_item_id="123456789", title=title,
        shop_name="普通店铺", shop_type="other", shop_verified=True,
    )
    quote = JdAdapter(None).quote_from_observation(
        listing, listing.url, title,
        f"{title} ¥3339.00 领券活动 到手价 ¥90 商品详情",
        [], ["普通店铺"], [], "", require_primary=True,
    )
    assert quote.page_price_cents == 333900
    assert quote.effective_price_cents == 333900
    assert quote.confidence == "high"
    assert quote.coupon_discount_cents is None
    assert quote.error is None


def test_jd_515_label_does_not_replace_4184_main_price():
    title = "vivoiQOO Neo11 至尊版 16GB+512GB乘风 2K护眼超冠屏 9100mAh蓝海大电池"
    listing = Listing(
        id=2, url="https://item.jd.com/100305145887.html",
        platform_item_id="100305145887", title=title,
        shop_name="京东自营", shop_type="jd_official_self", shop_verified=True,
    )
    quote = JdAdapter(None).quote_from_observation(
        listing, listing.url, title,
        f"{title} 收藏 ¥4184.00 到手价 ¥515 满500减10 直降600元 领后减￥500 商品详情",
        [], ["京东自营"], [], "", require_primary=True,
    )
    assert quote.effective_price_cents == 418400
    assert quote.confidence == "high"
    assert not any(item["applied"] for item in quote.coupon_breakdown)


def test_generic_subsidy_text_does_not_hide_anchored_page_price():
    title = "莫森（MOSEN）MS-33C 手机支架 61到88英寸双管加粗加厚便携"
    listing = Listing(
        id=4, url="https://item.jd.com/100014001708.html",
        platform_item_id="100014001708", title=title,
        shop_name="京东自营", shop_type="jd_official_self", shop_verified=True,
    )
    quote = JdAdapter(None).quote_from_observation(
        listing, listing.url, title,
        f"{title} 收藏 ¥78.53 已享受：平台补贴 满200减25 商品详情",
        [], ["京东自营"], [], "", require_primary=True,
    )
    assert quote.page_price_cents == 7853
    assert quote.effective_price_cents == 7853
    assert quote.confidence == "high"
    assert not any(item["applied"] for item in quote.coupon_breakdown)


async def test_price_fetch_uses_pc_item_page_only(monkeypatch):
    adapter = JdAdapter(None)
    seen = []

    async def fetch_quote(listing, account, target_url):
        seen.append(target_url)
        return target_url

    monkeypatch.setattr(adapter, "_fetch_page_quote", fetch_quote)
    listing = Listing(
        url="https://item.m.jd.com/product/10237128678205.html",
        platform_item_id="10237128678205",
    )
    account = Account(profile_dir="jd_profile")

    result = await adapter.fetch_page_price(listing, account)

    assert result == "https://item.jd.com/10237128678205.html"
    assert seen == [result]


async def test_forbidden_checkout_button_is_rejected():
    with pytest.raises(ValueError):
        await _click_exact_text(None, "提交订单")


def test_clean_jd_title():
    assert clean_title(
        "vivo iQOO Neo11 至尊版 12GB+256GB 【图片 价格 品牌 评论】-京东"
    ) == "vivo iQOO Neo11 至尊版 12GB+256GB"
    assert clean_title("iQOO Neo12 12GB 512GB-京东") == "iQOO Neo12 12GB 512GB"


def test_parse_specs_from_title():
    assert parse_specs("iQOO Neo11 至尊版 12GB+512GB") == {
        "ram_gb": "12",
        "storage_gb": "512",
    }
    assert parse_specs("vivo iQOO Neo12 12GB 512GB 官方标配") == {
        "ram_gb": "12",
        "storage_gb": "512",
    }
    assert parse_specs("Apple iPhone 17 Pro 256GB") == {}
