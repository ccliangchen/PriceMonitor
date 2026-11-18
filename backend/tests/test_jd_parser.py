from pathlib import Path

from bs4 import BeautifulSoup

from app.adapters.jd.parser import (
    extract_embedded_price_cents,
    extract_embedded_promotion_price_cents,
    extract_sku,
    parse_checkout_payable_cents,
    parse_product_page,
    parse_sku_variants,
)


def test_real_item_page_fixture():
    fixture = Path(__file__).parent / "fixtures" / "jd" / "item_page.html"
    html = fixture.read_text(encoding="utf-8")
    soup = BeautifulSoup(html, "lxml")

    parsed = parse_product_page(
        url="https://item.jd.com/100396381212.html",
        title=soup.title.get_text(strip=True) if soup.title else "",
        body_text=soup.body.get_text("\n", strip=True) if soup.body else "",
        price_texts=[
            element.get_text(" ", strip=True)
            for element in soup.select(".p-price .price")
        ],
        shop_texts=[
            element.get_text(" ", strip=True)
            for element in soup.select(".shopName")
        ],
        embedded_price_cents=extract_embedded_price_cents(html),
    )

    assert parsed.shop_type == "jd_official_self"
    assert parsed.page_price_cents == 369900
    assert parsed.estimated_price_cents == 349900
    assert parsed.confidence == "high"
    assert extract_embedded_promotion_price_cents(html) == 349900
    raw_coupons = " ".join(item["raw"] for item in parsed.coupon_breakdown)
    assert "立减200元" in raw_coupons
    assert "满3000减100" in raw_coupons


def test_self_operated_with_threshold_coupon():
    parsed = parse_product_page(
        url="https://item.jd.com/100.html",
        title="iQOO Neo11 至尊版 12GB+512GB",
        body_text="京东价 ￥7499.00 满3000减300 京东自营",
        price_texts=["￥7,499.00"],
        shop_texts=["iQOO京东自营旗舰店"],
    )

    assert parsed.shop_type == "jd_official_self"
    assert parsed.evidence["self_operated"] == "true"
    assert parsed.page_price_cents == 749900
    assert parsed.coupon_discount_cents == 30000
    assert parsed.estimated_price_cents == 719900
    assert parsed.confidence == "low"
    assert parsed.status == "ok"


def test_to_price_wins_over_page_price():
    parsed = parse_product_page(
        url="https://item.jd.com/100.html",
        title="iQOO Neo11 至尊版 12GB+512GB",
        body_text="到手价 ￥6999.00 京东价 ￥7499.00 官方旗舰店",
        price_texts=["￥7,499.00"],
        shop_texts=["iQOO官方旗舰店"],
    )

    assert parsed.shop_type == "official_flagship"
    assert parsed.evidence["official_badge"] == "true"
    assert parsed.page_price_cents == 749900
    assert parsed.estimated_price_cents == 699900
    assert parsed.coupon_discount_cents == 50000


def test_recommended_self_operated_shop_does_not_override_current_seller():
    parsed = parse_product_page(
        url="https://item.jd.com/100.html",
        title="iQOO Neo12",
        body_text="京东价 ￥4899.00 iQOO官方旗舰店 猜你喜欢 某某京东自营旗舰店",
        price_texts=["￥4899.00"],
        shop_texts=["iQOO官方旗舰店"],
    )
    assert parsed.shop_type == "official_flagship"
    assert parsed.shop_name == "iQOO官方旗舰店"


def test_already_applied_subsidy_is_not_subtracted_twice():
    parsed = parse_product_page(
        url="https://item.jd.com/100.html",
        title="iQOO Neo11",
        body_text=(
            "¥3193.48 国补领后价 ¥3699 已享受：限时立减5 "
            "国家补贴｜领后减￥500 可再享：最高返159京豆"
        ),
        price_texts=["¥3193.48"],
        shop_texts=["iQOO京东自营旗舰店"],
    )
    assert parsed.page_price_cents == 319348
    assert parsed.estimated_price_cents == 319348
    assert parsed.coupon_discount_cents == 0
    assert parsed.confidence == "high"


def test_available_coupon_without_applied_section_stays_low_confidence():
    parsed = parse_product_page(
        url="https://item.jd.com/100.html",
        title="iQOO Neo11",
        body_text="京东价 ￥3999.00 可再享：国家补贴｜领后减￥500",
        price_texts=["￥3999.00"],
        shop_texts=["iQOO京东自营旗舰店"],
    )
    assert parsed.confidence == "low"


def test_login_prompt_inside_product_page_does_not_hide_visible_price():
    parsed = parse_product_page(
        url="https://item.jd.com/100.html",
        title="iQOO Neo11 至尊版",
        body_text="京东价 ￥7499.00 到手价 ￥6999.00 领券请登录 京东自营",
        price_texts=["￥7499.00"],
        shop_texts=["iQOO京东自营旗舰店"],
    )
    assert parsed.status == "ok"
    assert parsed.estimated_price_cents == 699900


def test_flagship_without_official_is_unknown():
    parsed = parse_product_page(
        url="https://item.jd.com/100.html",
        title="iQOO Neo11",
        body_text="京东价 ￥7499.00 旗舰店",
        price_texts=["￥7499.00"],
        shop_texts=["某某旗舰店"],
    )

    assert parsed.shop_type == "unknown"
    assert parsed.evidence["official_badge"] == "false"


def test_other_shop_is_rejected_by_type():
    parsed = parse_product_page(
        url="https://item.jd.com/100.html",
        title="iQOO Neo11",
        body_text="京东价 ￥7499.00 专卖店",
        price_texts=["￥7499.00"],
        shop_texts=["某某手机专卖店"],
    )

    assert parsed.shop_type == "other"


def test_missing_price_is_parse_error():
    parsed = parse_product_page(
        url="https://item.jd.com/100.html",
        title="iQOO Neo11",
        body_text="欢迎光临",
        price_texts=[],
        shop_texts=["iQOO京东自营旗舰店"],
    )

    assert parsed.status == "parse_error"
    assert parsed.error


def test_coupon_below_threshold_not_applied():
    parsed = parse_product_page(
        url="https://item.jd.com/100.html",
        title="iQOO Neo11",
        body_text="京东价 ￥2000.00 满3000减300 京东自营",
        price_texts=["￥2000.00"],
        shop_texts=["iQOO京东自营旗舰店"],
    )

    assert parsed.coupon_discount_cents == 0
    assert parsed.estimated_price_cents == 200000
    assert parsed.coupon_breakdown[0]["applied"] is False


def test_price_in_long_body_with_installment_words_is_found():
    parsed = parse_product_page(
        url="https://item.m.jd.com/product/100396381212.html",
        title="vivoiQOO Neo11 至尊版 12GB+256GB乘风",
        body_text=(
            "1/9 | ¥3698.00 | 登录最高省10% | 京东自营 | "
            "价格说明：支持分期付款，部分用户可享12期免息。"
        ),
        price_texts=[],
        shop_texts=["iQOO京东自营旗舰店"],
    )

    assert parsed.status == "ok"
    assert parsed.page_price_cents == 369800
    assert parsed.estimated_price_cents == 369800


def test_installment_text_is_not_used_as_price():
    parsed = parse_product_page(
        url="https://item.jd.com/100.html",
        title="iQOO Neo11",
        body_text="京东价 ￥7499.00 京东自营",
        price_texts=["￥600/月"],
        shop_texts=["iQOO京东自营旗舰店"],
    )

    assert parsed.page_price_cents == 749900


def test_self_operated_shop_name_uses_first_line():
    parsed = parse_product_page(
        url="https://item.m.jd.com/product/100396381212.html",
        title="vivoiQOO Neo11 至尊版 12GB+256GB乘风",
        body_text="京东价 ￥3698.00 京东自营",
        price_texts=[],
        shop_texts=["iQOO京东自营旗舰店\n600+商品\n3479万+关注"],
    )

    assert parsed.shop_type == "jd_official_self"
    assert parsed.evidence["self_operated"] == "true"
    assert parsed.shop_name == "iQOO京东自营旗舰店"
    assert parsed.page_price_cents == 369800


def test_mobile_page_body_is_parsed():
    parsed = parse_product_page(
        url="https://item.m.jd.com/product/10237128678205.html",
        title=(
            "vivo iQOO Neo12 2K 185Hz超冠屏 第五代骁龙8至尊版 "
            "12GB 512GB 官方标配【图片 价格 品牌 评论】-京东"
        ),
        body_text=(
            "滑动查看详情 | 1/10 | ¥4899.00 | 登录最高省15% | "
            "vivo iQOO Neo12 2K 185Hz超冠屏 | 优惠 | 赠品 | "
            "iQOO官方旗舰店 | 61件商品 | 评价 9.50高 | 包邮"
        ),
        price_texts=[],
        shop_texts=[],
    )

    assert parsed.shop_type == "official_flagship"
    assert parsed.evidence["official_badge"] == "true"
    assert parsed.shop_name == "iQOO官方旗舰店"
    assert parsed.page_price_cents == 489900
    assert parsed.estimated_price_cents == 489900
    assert parsed.confidence == "high"
    assert parsed.status == "ok"


def test_guobu_final_price_label_wins_over_jd_price():
    parsed = parse_product_page(
        url="https://item.jd.com/10237128678205.html",
        title="vivo iQOO Neo12 12GB+512GB 官方标配",
        body_text=(
            "京东价 ￥4899.00 国补后价 ￥3848.78 "
            "已享：国家补贴 领后减¥500 满4000减550 "
            "可再享：赠品 最高返192京豆"
        ),
        price_texts=["￥4899.00"],
        shop_texts=["iQOO官方旗舰店"],
    )

    assert parsed.page_price_cents == 489900
    assert parsed.estimated_price_cents == 384878
    assert parsed.coupon_discount_cents == 105022
    assert parsed.confidence == "high"
    raws = " ".join(item["raw"] for item in parsed.coupon_breakdown)
    assert "领后减" in raws
    assert "满4000减550" in raws


def test_applied_coupons_compute_final_price_without_final_label():
    parsed = parse_product_page(
        url="https://item.jd.com/10237128678205.html",
        title="vivo iQOO Neo12 12GB+512GB 官方标配",
        body_text=(
            "京东价 ￥4899.00 已享：国家补贴 领后减¥500 满4000减550"
        ),
        price_texts=["￥4899.00"],
        shop_texts=["iQOO官方旗舰店"],
    )

    assert parsed.page_price_cents == 489900
    assert parsed.estimated_price_cents == 384900
    assert parsed.confidence == "low"


def test_coupon_amount_cannot_become_high_confidence_product_price():
    parsed = parse_product_page(
        url="https://item.jd.com/100305145887.html",
        title="iQOO Neo11",
        body_text="国补领后价 ￥500 已享受：国家补贴 领后减￥500",
        price_texts=["￥500"],
        shop_texts=["iQOO京东自营旗舰店"],
    )
    assert parsed.page_price_cents == 50000
    assert parsed.confidence == "low"


def test_embedded_promotion_and_seckill_price():
    html = (
        '"promov2":[{"pis":[{"customtag":"{\\"p\\":\\"3498.00\\"}"}]}],'
        '"seckill":{"jdPrice":"3699.0","miaoShaPrice":"3498.0"}'
    )

    assert extract_embedded_promotion_price_cents(html) == 349800


def test_embedded_json_price_is_extracted():
    html = (
        '"priceFloor": {"demoteEnable":false,"price":"\\uebb3...",'
        '"fontFamily":"JDZH-Regular-Price","type":"251",'
        '"ext":{"jdPrice":"4899.00","realPriceExt":{"ORIGINAL":{}}}}'
    )

    assert extract_embedded_price_cents(html) == 489900


def test_obfuscated_price_uses_embedded_value():
    parsed = parse_product_page(
        url="https://item.m.jd.com/product/10237128678205.html",
        title="vivo iQOO Neo12 12GB 512GB",
        body_text="1/10 | ¥. | iQOO官方旗舰店",
        embedded_price_cents=489900,
    )

    assert parsed.status == "ok"
    assert parsed.page_price_cents == 489900
    assert parsed.estimated_price_cents == 489900
    assert parsed.shop_type == "official_flagship"


def test_parse_sku_variants():
    html = (
        '<script>var x=[{"color":"驰光白","imagePath":"x","spec":"官方标配",'
        '"size":"16GB+512GB","skuId":"100305146259"},'
        '{"color":"疾影黑","spec":"官方标配","size":"12GB+256GB","skuId":"100305258657"}];</script>'
    )

    variants = parse_sku_variants(html)

    assert len(variants) == 2
    assert variants[0].color == "驰光白"
    assert (variants[0].ram_gb, variants[0].storage_gb) == (16, 512)
    assert variants[0].sku_id == "100305146259"
    assert variants[0].url.endswith("/100305146259.html")
    assert (variants[1].ram_gb, variants[1].storage_gb) == (12, 256)


def test_login_and_captcha_are_detected():
    login = parse_product_page(
        url="https://passport.jd.com/new/login.aspx",
        title="京东登录",
        body_text="请登录",
    )
    captcha = parse_product_page(
        url="https://cfe.m.jd.com/privatedomain/risk_handler/",
        title="京东验证",
        body_text="验证一下",
    )

    assert login.status == "login_required"
    assert captcha.status == "captcha"


def test_parse_checkout_payable():
    assert parse_checkout_payable_cents("应付总额 ￥3,698.00") == 369800
    assert parse_checkout_payable_cents("需付款：2699.00元") == 269900
    assert parse_checkout_payable_cents("没有金额") is None


def test_extract_sku():
    assert extract_sku("https://item.jd.com/100012043978.html") == "100012043978"
    assert extract_sku("https://item.m.jd.com/product/100012043978.html") == "100012043978"
    assert extract_sku("https://u.jd.com/abc") is None
