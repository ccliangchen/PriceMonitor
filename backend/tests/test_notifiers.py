import httpx
import pytest
import respx

from app.adapters.base import PriceQuote
from app.core.models import Listing, Product, ProductPriceSnapshot
from app.notifiers.base import NotificationMessage
from app.notifiers.serverchan import ServerChanNotifier
from app.services.notifications import build_new_low_message, format_cents


@respx.mock
async def test_serverchan_send_success():
    route = respx.post("https://sctapi.ftqq.com/TESTKEY.send").mock(
        return_value=httpx.Response(200, json={"code": 0, "data": {}})
    )

    await ServerChanNotifier("TESTKEY").send(
        NotificationMessage(title="测试标题", body="测试正文")
    )

    assert route.called
    request = route.calls[0].request
    body = request.content.decode("utf-8")
    assert "title=" in body
    assert "desp=" in body


@respx.mock
async def test_serverchan_send_error_code():
    respx.post("https://sctapi.ftqq.com/TESTKEY.send").mock(
        return_value=httpx.Response(200, json={"code": 1, "message": "bad key"})
    )

    with pytest.raises(RuntimeError):
        await ServerChanNotifier("TESTKEY").send(
            NotificationMessage(title="测试", body="正文")
        )


def test_format_cents():
    assert format_cents(749900) == "¥7,499"
    assert format_cents(749950) == "¥7,499.50"


def test_build_new_low_message_contains_details():
    product = Product(
        name="iQOO Neo11 至尊版 12GB+512GB",
        brand="iQOO",
        model="Neo11",
        variant="至尊版",
        ram_gb=12,
        storage_gb=512,
        canonical_key="iqoo|neo11|至尊版|12|512|",
    )
    listing = Listing(
        product=product,
        platform="jd",
        shop_name="iQOO京东自营旗舰店",
        shop_type="jd_official_self",
        shop_verified=True,
        url="https://item.jd.com/100.html",
        platform_item_id="100",
        title=product.name,
    )
    quote = PriceQuote(
        platform="jd",
        listing_id=1,
        source="page",
        effective_price_cents=729900,
        coupon_breakdown=[{"raw": "满3000减300", "applied": True}],
    )
    snapshot = ProductPriceSnapshot(
        product_id=1,
        lowest_price_cents=729900,
        lowest_platform="jd",
        lowest_listing_id=1,
        previous_low_cents=749900,
        is_new_low=True,
        coverage={"jd": "ok"},
        source_mix={"jd": "page"},
    )

    message = build_new_low_message(product, listing, quote, snapshot)

    assert "京东预估新低" in message.title
    assert "¥7,299" in message.title
    assert "原史低" in message.body
    assert "¥7,499" in message.body
    assert "满3000减300" in message.body
    assert "iQOO京东自营旗舰店" in message.body


def test_high_confidence_page_new_low_message():
    product = Product(
        name="iQOO Neo11 至尊版 12GB+512GB",
        brand="iQOO",
        model="Neo11",
        variant="至尊版",
        ram_gb=12,
        storage_gb=512,
        canonical_key="iqoo|neo11|至尊版|12|512|",
    )
    listing = Listing(
        product=product,
        platform="taobao",
        shop_name="iQOO手机官方旗舰店",
        shop_type="official_flagship",
        shop_verified=True,
        url="https://detail.tmall.com/item.htm?id=1",
        platform_item_id="1",
        title=product.name,
    )
    quote = PriceQuote(
        platform="taobao",
        listing_id=1,
        source="page",
        confidence="high",
        effective_price_cents=319410,
    )
    snapshot = ProductPriceSnapshot(
        product_id=1,
        lowest_price_cents=319410,
        lowest_platform="taobao",
        lowest_listing_id=1,
        previous_low_cents=369900,
        is_new_low=True,
        coverage={"taobao": "ok"},
        source_mix={"taobao": "page"},
    )

    message = build_new_low_message(product, listing, quote, snapshot)

    assert "淘宝页面新低" in message.title
    assert "（页面预估价）" in message.title
    assert "页面预估价" in message.body


def test_build_taobao_checkout_new_low_message():
    product = Product(
        name="iQOO Neo11 至尊版 12GB+512GB",
        brand="iQOO",
        model="Neo11",
        variant="至尊版",
        ram_gb=12,
        storage_gb=512,
        canonical_key="iqoo|neo11|至尊版|12|512|",
    )
    listing = Listing(
        product=product,
        platform="taobao",
        shop_name="iQOO手机官方旗舰店",
        shop_type="official_flagship",
        shop_verified=True,
        url="https://detail.tmall.com/item.htm?id=1",
        platform_item_id="1",
        title=product.name,
    )
    quote = PriceQuote(
        platform="taobao",
        listing_id=2,
        source="checkout",
        effective_price_cents=419900,
    )
    snapshot = ProductPriceSnapshot(
        product_id=1,
        lowest_price_cents=419900,
        lowest_platform="taobao",
        lowest_listing_id=2,
        previous_low_cents=439900,
        is_new_low=True,
        coverage={"taobao": "ok"},
        source_mix={"taobao": "checkout"},
    )

    message = build_new_low_message(product, listing, quote, snapshot)

    assert message.title.startswith("淘宝实付新低")
    assert "实付结算价" in message.body
    assert "平台**：淘宝" in message.body
    assert "iQOO手机官方旗舰店" in message.body
