import json
from pathlib import Path

from bs4 import BeautifulSoup

from app.adapters.taobao.parser import (
    choose_title,
    extract_embedded_price_cents,
    extract_embedded_shop_name,
    extract_ice_context,
    extract_item_id,
    extract_sku_id,
    extract_ssr_sku_info,
    extract_ssr_sku_price_cents,
    extract_taobao_sku_variants,
    parse_checkout_payable_cents,
    parse_product_page,
    parse_shop_search_results,
    parse_store_search_items,
)


def test_official_flagship_with_coupon():
    parsed = parse_product_page(
        url="https://detail.tmall.com/item.htm?id=100",
        title="vivo iQOO Neo11 12GB+256GB",
        body_text="券后价 ￥2699.00 原价 ￥2999.00 满3000减300",
        price_texts=["￥2999.00"],
        shop_texts=["iQOO手机官方旗舰店"],
    )

    assert parsed.shop_type == "official_flagship"
    assert parsed.evidence["official_badge"] == "true"
    assert parsed.shop_name == "iQOO手机官方旗舰店"
    assert parsed.page_price_cents == 299900
    assert parsed.estimated_price_cents == 269900
    assert parsed.status == "ok"


def test_flagship_without_official_keyword_is_unknown():
    parsed = parse_product_page(
        url="https://detail.tmall.com/item.htm?id=100",
        title="iQOO Neo11",
        body_text="￥2999.00",
        price_texts=["￥2999.00"],
        shop_texts=["某某数码旗舰店"],
    )

    assert parsed.shop_type == "unknown"
    assert parsed.evidence["official_badge"] == "false"


def test_shop_title_alone_does_not_qualify():
    parsed = parse_product_page(
        url="https://detail.tmall.com/item.htm?id=100",
        title="iQOO官方旗舰店 iQOO Neo11 12GB+256GB",
        body_text="￥2999.00",
        price_texts=["￥2999.00"],
        shop_texts=["某某数码专营店"],
    )

    assert parsed.shop_type == "other"


def test_subsidy_after_price_label():
    parsed = parse_product_page(
        url="https://detail.tmall.com/item.htm?id=1063055019530",
        title="【享15%国家补贴】iQOO Neo11 至尊版 12GB+512GB",
        body_text=(
            "补贴后 ￥3194.1 优惠前 ￥4399 "
            "已享受: 闪电加补700元 | 满1500减150 政府补贴10%"
        ),
        price_texts=["￥3194.1", "￥4399"],
        shop_texts=["iQOO手机官方旗舰店"],
    )

    assert parsed.status == "ok"
    assert parsed.page_price_cents == 439900
    assert parsed.estimated_price_cents == 319410
    assert parsed.coupon_discount_cents == 120490
    raw_coupons = " ".join(item["raw"] for item in parsed.coupon_breakdown)
    assert "闪电加补700元" in raw_coupons
    assert "满1500减150" in raw_coupons
    assert "政府补贴10%" in raw_coupons


def test_degraded_page_is_not_used():
    parsed = parse_product_page(
        url="https://detail.tmall.com/item.htm?id=1063055019530",
        title="iQOO Neo11 至尊版",
        body_text=(
            "访问异常提示 系统检测到当前访问存在异常，请恢复后再访问 "
            "优惠前 ￥4399"
        ),
        price_texts=["￥4399"],
        shop_texts=["iQOO手机官方旗舰店"],
    )

    assert parsed.status == "parse_error"
    assert "访问异常" in (parsed.error or "")


def test_coupon_threshold_is_applied():
    parsed = parse_product_page(
        url="https://detail.tmall.com/item.htm?id=100",
        title="iQOO Neo11",
        body_text="￥2999.00 满3000减300 店铺券100元",
        price_texts=["￥2999.00"],
        shop_texts=["iQOO手机官方旗舰店"],
    )

    assert parsed.coupon_discount_cents == 0
    assert parsed.estimated_price_cents == 299900
    assert parsed.coupon_breakdown[0]["applied"] is False


def test_original_price_is_not_used_when_sale_price_exists():
    parsed = parse_product_page(
        url="https://detail.tmall.com/item.htm?id=100",
        title="iQOO Neo11",
        body_text="原价 ￥3999.00 售价 ￥2999.00",
        price_texts=["￥3999.00", "￥2999.00"],
        shop_texts=["iQOO手机官方旗舰店"],
    )

    assert parsed.page_price_cents == 299900
    assert parsed.estimated_price_cents == 299900


def test_missing_price_is_parse_error():
    parsed = parse_product_page(
        url="https://detail.tmall.com/item.htm?id=100",
        title="iQOO Neo11",
        body_text="欢迎光临",
        price_texts=[],
        shop_texts=["iQOO手机官方旗舰店"],
    )

    assert parsed.status == "parse_error"
    assert parsed.error


def test_login_and_punish_are_detected():
    login = parse_product_page(
        url="https://login.taobao.com/member/login.jhtml",
        title="登录",
        body_text="请登录",
    )
    captcha = parse_product_page(
        url="https://detail.tmall.com/item.htm?_____tmd_____=1&id=100",
        title="验证码拦截",
        body_text="请拖动滑块",
    )

    assert login.status == "login_required"
    assert captcha.status == "captcha"


def test_choose_title_skips_generic_document_title():
    title = choose_title(
        "商品详情",
        ["用户评价", "vivo iQOO Neo11 至尊版 12GB+512GB 官方旗舰店"],
    )
    assert title == "vivo iQOO Neo11 至尊版 12GB+512GB 官方旗舰店"
    assert choose_title("商品详情", []) == "商品详情"
    assert choose_title("", []) == ""
    assert choose_title(
        "商品详情",
        ["vivo iQOO Neo12 12GB+512GB-tmall.com天猫"],
    ) == "vivo iQOO Neo12 12GB+512GB"


def test_embedded_price_extraction():
    html = '"data":{"price":"2999.00","promotionPrice":"2699.00"}'
    assert extract_embedded_price_cents(html) == 269900
    assert extract_embedded_price_cents('"priceText":"￥2,699.00"') == 269900


def test_ssr_sku_price_extraction():
    context = {
        "loaderData": {
            "home": {
                "data": {
                    "res": {
                        "skuCore": {
                            "sku2info": {
                                "6316125282916": {
                                    "price": {
                                        "priceTitle": "优惠前",
                                        "priceText": "4399",
                                        "priceMoney": "439900",
                                    },
                                    "subPrice": {
                                        "priceTitle": "券后",
                                        "priceText": "3194.1",
                                        "priceMoney": "319410",
                                    },
                                    "quantity": 200,
                                    "quantityText": "有货(限购2件)",
                                    "limit": "2",
                                }
                            }
                        }
                    }
                }
            }
        }
    }
    html = (
        "<script>window.__ICE_APP_CONTEXT__="
        + json.dumps(context)
        + ";</script>"
    )

    assert extract_ice_context(html) == context
    assert extract_ssr_sku_price_cents(html, "6316125282916") == 319410
    info = extract_ssr_sku_info(html, "6316125282916")
    assert info is not None
    assert info.price_cents == 439900
    assert info.price_title == "优惠前"
    assert info.sub_price_cents == 319410
    assert info.sub_price_title == "券后"
    assert info.quantity == 200
    assert info.limit == 2
    assert "有货" in info.stock_text
    assert extract_ssr_sku_price_cents(html, "other") is None
    assert extract_ssr_sku_price_cents(html, None) is None


def test_embedded_shop_name_extraction():
    html = '"sellerId":"883737303","shopName":"iQOO手机官方旗舰店","tmall":true'
    assert extract_embedded_shop_name(html) == "iQOO手机官方旗舰店"


def test_real_item_page_fixture():
    fixture = Path(__file__).parent / "fixtures" / "taobao" / "item_page.html"
    html = fixture.read_text(encoding="utf-8")
    soup = BeautifulSoup(html, "lxml")

    title = choose_title(
        soup.title.get_text(strip=True) if soup.title else "",
        [
            element.get_text(" ", strip=True)
            for element in soup.select("[class*='Title']")
        ],
    )
    embedded_shop = extract_embedded_shop_name(html)
    shop_texts = [
        element.get("title") or element.get_text(" ", strip=True)
        for element in soup.select("[class*='shopName']")
    ]
    if embedded_shop:
        shop_texts = [embedded_shop, *shop_texts]
    body = soup.body.get_text("\n", strip=True)
    price_texts = [
        element.get_text(" ", strip=True)
        for element in soup.select("[class*='price']")
    ]

    parsed = parse_product_page(
        url="https://detail.tmall.com/item.htm?id=1085089124325",
        title=title,
        body_text=body,
        price_texts=price_texts,
        shop_texts=shop_texts,
        embedded_price_cents=extract_embedded_price_cents(html),
    )

    assert title.startswith("【赠充电宝】vivo iQOO Neo12")
    assert title.endswith("国补")
    assert parsed.shop_type == "official_flagship"
    assert parsed.shop_name == "iQOO手机官方旗舰店"
    assert parsed.page_price_cents == 419900
    assert parsed.estimated_price_cents == 419900
    assert parsed.status == "ok"


def test_parse_checkout_payable():
    assert parse_checkout_payable_cents("实付款 ￥2,699.00") == 269900
    assert parse_checkout_payable_cents("合计：2999.00") == 299900
    assert parse_checkout_payable_cents("没有金额") is None


def test_extract_ids():
    url = "https://detail.tmall.com/item.htm?id=824950233983&skuId=4403221617613"
    assert extract_item_id(url) == "824950233983"
    assert extract_sku_id(url) == "4403221617613"
    assert extract_item_id("https://item.taobao.com/item.htm?id=123456") == "123456"
    assert extract_item_id("https://uland.taobao.com/coupon/edetail?itemId=123456") == "123456"
    assert extract_item_id("https://m.tb.cn/h.abcd") is None


def test_shop_search_extracts_shop_names_without_product_title_noise():
    fixture = Path(__file__).parent / "fixtures" / "taobao" / "shop_search.html"
    stores = parse_shop_search_results(fixture.read_text(encoding="utf-8"))

    assert stores[0].name == "iQOO手机官方旗舰店"
    assert stores[0].url == "https://shop71799145.taobao.com/category.htm"
    assert any("Neo11" in item.title for item in stores[0].sample_items)
    assert any("专卖店" in store.name for store in stores)
    # A product title containing "官方旗舰店" must not turn a 专卖店 into an
    # official flagship store.
    assert all(
        store.name == "iQOO华大专卖店" or "官方旗舰店" in store.name
        for store in stores
    )


def test_store_search_items_are_deduped_and_keep_titles():
    fixture = Path(__file__).parent / "fixtures" / "taobao" / "store_search.html"
    items = parse_store_search_items(fixture.read_text(encoding="utf-8"))

    by_id = {item.item_id: item for item in items}
    assert "1064830909687" in by_id
    assert "Neo11 至尊版" in by_id["1064830909687"].title
    assert by_id["1064830909687"].url.startswith(
        "https://item.taobao.com/item.htm?id=1064830909687"
    )


def test_ssr_sku_variants_extract_ram_storage_color_and_sku_url():
    fixture = Path(__file__).parent / "fixtures" / "taobao" / "item_skus.html"
    variants = extract_taobao_sku_variants(
        fixture.read_text(encoding="utf-8"),
        "https://detail.tmall.com/item.htm?id=1064830909687",
    )

    assert len(variants) == 9
    target = next(
        item
        for item in variants
        if item.ram_gb == 12 and item.storage_gb == 512 and item.color == "乘风"
    )
    assert target.spec == "官方标配"
    assert target.sku_id == "6316034474209"
    assert target.url == (
        "https://detail.tmall.com/item.htm?id=1064830909687"
        "&skuId=6316034474209"
    )


def test_ssr_sku_variants_missing_context_is_empty():
    assert extract_taobao_sku_variants("<html></html>") == []
