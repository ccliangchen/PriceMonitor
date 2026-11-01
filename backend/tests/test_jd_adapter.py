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
from app.core.exceptions import CaptchaRequired, ParseError, ShopNotAllowed
from app.core.models import Listing


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
    with pytest.raises(CaptchaRequired):
        JdAdapter._assert_not_blocked(  # noqa: SLF001
            "https://item.m.jd.com/product/1.html",
            "京东",
            "抱歉，访问频繁，请稍后再试",
        )


async def test_forbidden_checkout_button_is_rejected():
    with pytest.raises(ValueError):
        await _click_exact_text(None, "提交订单")


def test_shop_change_is_rejected():
    listing = Listing(shop_name="iQOO京东自营旗舰店")

    with pytest.raises(ShopNotAllowed):
        JdAdapter._assert_shop_unchanged(  # noqa: SLF001
            listing,
            "某某数码专营店",
        )

    JdAdapter._assert_shop_unchanged(  # noqa: SLF001
        listing,
        "iQOO京东自营旗舰店（官方）",
    )


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
