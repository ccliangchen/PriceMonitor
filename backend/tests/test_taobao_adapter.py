import pytest

from app.adapters.taobao.adapter import (
    TaobaoAdapter,
    _click_exact_text,
    has_login_cookies,
    normalize_url,
    parse_specs,
)
from app.core.exceptions import ParseError, ShopNotAllowed
from app.core.models import Listing


def test_has_login_cookies():
    assert has_login_cookies(
        [{"name": "unb", "value": "123"}, {"name": "tracknick", "value": "me"}]
    )
    assert has_login_cookies(
        [{"name": "unb", "value": "123"}, {"name": "cookie17", "value": "me"}]
    )
    assert not has_login_cookies([{"name": "unb", "value": "123"}])
    assert not has_login_cookies([{"name": "cookie2", "value": "x"}])
    assert not has_login_cookies([])


def test_normalize_url_accepts_taobao_hosts():
    assert normalize_url("item.taobao.com/item.htm?id=1") == (
        "https://item.taobao.com/item.htm?id=1"
    )
    assert normalize_url("https://detail.tmall.com/item.htm?id=1") == (
        "https://detail.tmall.com/item.htm?id=1"
    )
    assert normalize_url("https://m.tb.cn/h.abcd") == "https://m.tb.cn/h.abcd"
    assert normalize_url(
        "https://detail.tmall.com/item.htm?fpChannel=101&fpChannelSig=abc&id=123&skuId=456"
    ) == "https://detail.tmall.com/item.htm?id=123&skuId=456"
    assert normalize_url(
        "https://item.taobao.com/item.htm?spm=a1z10&id=789"
    ) == "https://item.taobao.com/item.htm?id=789"


def test_normalize_url_rejects_other_hosts():
    with pytest.raises(ParseError):
        normalize_url("https://example.com/item.htm?id=1")
    with pytest.raises(ParseError):
        normalize_url("")


def test_parse_specs_from_title():
    assert parse_specs("iQOO Neo11 12GB+256GB") == {
        "ram_gb": "12",
        "storage_gb": "256",
    }
    assert parse_specs("iQOO Neo11 12GB 512GB") == {
        "ram_gb": "12",
        "storage_gb": "512",
    }
    assert parse_specs("iQOO Neo11 至尊版 12G+512G") == {
        "ram_gb": "12",
        "storage_gb": "512",
    }


async def test_forbidden_checkout_button_is_rejected():
    with pytest.raises(ValueError):
        await _click_exact_text(None, "立即支付")


def test_shop_change_is_rejected():
    listing = Listing(shop_name="iQOO手机官方旗舰店")

    with pytest.raises(ShopNotAllowed):
        TaobaoAdapter._assert_shop_unchanged(  # noqa: SLF001
            listing,
            "某某数码专营店",
        )

    TaobaoAdapter._assert_shop_unchanged(  # noqa: SLF001
        listing,
        "iQOO手机官方旗舰店（天猫）",
    )
