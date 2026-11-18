import json
from contextlib import asynccontextmanager

import pytest

from app.adapters.taobao.adapter import (
    TaobaoAdapter,
    _click_exact_text,
    _listing_target,
    has_login_cookies,
    normalize_url,
    parse_specs,
)
from app.core.exceptions import CaptchaRequired, ParseError
from app.core.models import Account, Listing


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


def test_passport_validation_redirect_is_a_retryable_captcha():
    with pytest.raises(CaptchaRequired, match="下轮自动重试"):
        TaobaoAdapter._assert_not_blocked(  # noqa: SLF001
            "https://passport.taobao.com/iv/normal_validate.htm",
            "安全验证",
            "页面正在验证账号",
        )


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


def test_taobao_navigation_keeps_pasted_referral_parameters():
    pasted = (
        "https://detail.tmall.com/item.htm?ali_refid=search123"
        "&id=1076349303771&priceTId=12345&skuId=6302158815917"
    )
    assert _listing_target(pasted) == pasted
    assert normalize_url(pasted) == (
        "https://detail.tmall.com/item.htm?id=1076349303771&skuId=6302158815917"
    )


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


def test_edge_observation_keeps_taobao_sku_checks_and_updates_shop():
    listing = Listing(
        id=3,
        platform="taobao",
        platform_item_id="1063055019530",
        platform_sku_id="6316125282916",
        shop_name="iQOO手机官方旗舰店",
        shop_type="official_flagship",
    )
    context = {
        "loaderData": {
            "sku2info": {
                "6316125282916": {
                    "price": {"priceText": "4399", "priceTitle": "优惠前"},
                    "subPrice": {"priceText": "3194.10", "priceTitle": "券后"},
                    "quantity": 20,
                }
            }
        }
    }
    html = '<script id="__ICE_APP_CONTEXT__">' + json.dumps(context) + '</script>'
    adapter = TaobaoAdapter(None)
    quote = adapter.quote_from_observation(
        listing,
        "https://detail.tmall.com/item.htm?id=1063055019530&skuId=6316125282916",
        "商品详情",
        "iQOO Neo11 至尊版 12GB+512GB 优惠前 ￥4399 券后价 ￥3194.10 领券减500 10元券 iQOO手机官方旗舰店",
        ["￥3194.10", "￥4399"],
        ["iQOO手机官方旗舰店"],
        [],
        html,
        ["iQOO Neo11 至尊版 12GB+512GB"],
    )

    assert quote.status == "ok"
    assert quote.confidence == "high"
    assert quote.page_price_cents == 439900
    assert quote.effective_price_cents == 319410
    assert quote.coupon_discount_cents == 120490
    assert quote.coupon_breakdown == [{
        "type": "页面已含优惠", "raw": "券后",
        "amount_cents": 120490, "applied": True,
    }]

    with pytest.raises(ParseError, match="其他商品"):
        adapter.quote_from_observation(
            listing,
            "https://detail.tmall.com/item.htm?id=99999999999",
            "商品详情",
            "iQOO Neo11 至尊版 12GB+512GB 优惠前 ￥4399 券后价 ￥3194.10",
            ["￥3194.10"],
            ["iQOO手机官方旗舰店"],
            [],
            html,
        )

    changed = adapter.quote_from_observation(
            listing,
            "https://detail.tmall.com/item.htm?id=1063055019530",
            "商品详情",
            "iQOO Neo11 至尊版 12GB+512GB 优惠前 ￥4399 券后价 ￥3194.10",
            ["￥3194.10"],
            ["某品牌官方旗舰店"],
            [],
            html,
        )
    assert changed.status == "ok"
    assert listing.shop_name == "某品牌官方旗舰店"


def test_regular_tmall_item_without_selected_sku_records_clear_page_price():
    listing = Listing(
        id=21,
        platform="taobao",
        platform_item_id="12345678901",
        platform_sku_id=None,
        shop_name="普通灯具店",
        shop_type="other",
    )
    quote = TaobaoAdapter(None).quote_from_observation(
        listing,
        "https://detail.tmall.com/item.htm?id=12345678901",
        "客厅台灯",
        "客厅台灯 商品详情 普通灯具店 现货包邮 售后保障 全国配送 支持退换货 ￥129",
        ["￥129"],
        ["普通灯具店"],
        [],
        "",
    )
    assert quote.status == "ok"
    assert quote.confidence == "high"
    assert quote.effective_price_cents == 12900


def test_selected_cheap_tmall_sku_uses_price_money_in_fen():
    listing = Listing(
        id=5, platform="taobao", platform_item_id="547652840450",
        platform_sku_id="3318388392453", shop_name="夏邑忆铭乐器专营店",
        shop_type="other",
    )
    context = {"loaderData": {"sku2info": {"3318388392453": {
        "price": {"priceText": "74", "priceMoney": "7400", "priceTitle": "优惠前"},
        "subPrice": {"priceText": "60.9", "priceMoney": "6090", "priceTitle": "券后"},
        "quantity": 12,
    }}}}
    html = '<script id="__ICE_APP_CONTEXT__">' + json.dumps(context) + '</script>'
    quote = TaobaoAdapter(None).quote_from_observation(
        listing,
        "https://detail.tmall.com/item.htm?id=547652840450&skuId=3318388392453",
        "电钢琴架U型琴架88电子琴架子76键键盘支架家用合成器通用型琴架",
        "电钢琴架U型琴架88电子琴架子76键键盘支架家用合成器通用型琴架 夏邑忆铭乐器专营店 优惠前 ￥74 券后 ￥60.9 商品详情",
        ["￥74", "￥60.9"], ["夏邑忆铭乐器专营店"], [], html,
    )
    assert quote.status == "ok"
    assert quote.confidence == "high"
    assert quote.page_price_cents == 7400
    assert quote.effective_price_cents == 6090
    assert quote.coupon_discount_cents == 1310


async def test_direct_resolve_rejects_degraded_item_page(monkeypatch):
    adapter = TaobaoAdapter(None)

    async def no_navigation(page, url):
        pass

    async def degraded_page(page):
        return (
            "某商品型号", "系统检测到当前访问存在异常 商品标题 ￥2999",
            ["￥2999"], ["某店铺"], [],
        )

    class Page:
        url = "https://detail.tmall.com/item.htm?id=1234567890"

        async def content(self):
            return "<html></html>"

    monkeypatch.setattr(adapter, "_goto", no_navigation)
    monkeypatch.setattr(adapter, "_read_page_settled", degraded_page)
    with pytest.raises(ParseError, match="访问异常/降级"):
        await adapter._resolve_page(Page(), Page.url)


async def test_direct_resolve_keeps_short_link_destination(monkeypatch):
    adapter = TaobaoAdapter(None)

    async def no_navigation(page, url):
        pass

    async def product_page(page):
        return (
            "某品牌新品商品型号", "某品牌新品商品型号 ￥2999 加入购物车 商品详情 正品保障 全国配送 售后保障 支持退换货",
            ["￥2999"], ["某品牌店铺"], [],
        )

    class Page:
        url = "https://detail.tmall.com/item.htm?id=1076349303771&skuId=6302158815917"

        async def content(self):
            return "<html></html>"

    monkeypatch.setattr(adapter, "_goto", no_navigation)
    monkeypatch.setattr(adapter, "_read_page_settled", product_page)
    info, _ = await adapter._resolve_page(Page(), "https://m.tb.cn/h.example")
    assert info.platform_item_id == "1076349303771"
    assert info.platform_sku_id == "6302158815917"
    assert info.url == Page.url


async def test_direct_price_capture_uses_saved_canonical_item_url(monkeypatch):
    visited = []
    pasted = (
        "https://detail.tmall.com/item.htm?ali_refid=search123"
        "&id=1076349303771&skuId=6302158815917"
    )
    canonical = "https://detail.tmall.com/item.htm?id=1076349303771&skuId=6302158815917"

    class Page:
        url = canonical

        async def content(self):
            return "<html></html>"

    class Browser:
        @asynccontextmanager
        async def session(self, profile_dir, headless):
            assert headless is True
            yield Page()

    adapter = TaobaoAdapter(Browser())

    async def goto(page, url):
        visited.append(url)

    async def read_page(page):
        return (
            "某品牌新品商品型号", "某品牌新品商品型号 ￥2999 加入购物车 商品详情 正品保障 全国配送 售后保障 支持退换货",
            ["￥2999"], ["某品牌店铺"], [],
        )

    monkeypatch.setattr(adapter, "_goto", goto)
    monkeypatch.setattr(adapter, "_read_page_settled", read_page)
    listing = Listing(
        id=1, platform="taobao", url=pasted, platform_item_id="1076349303771",
        platform_sku_id="6302158815917", shop_name="某品牌店铺", shop_type="other",
    )
    await adapter.fetch_page_price(listing, Account(platform="taobao", profile_dir="taobao_profile"))
    assert visited == [canonical]
