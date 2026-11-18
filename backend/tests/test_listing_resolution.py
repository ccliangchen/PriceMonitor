import pytest

from app.adapters.base import ListingInfo
from app.core.db import session_scope
from app.core.exceptions import LoginRequired, ParseError
from app.core.models import Account
from app.services.listing_resolution import resolve_with_browser_extension


def _info(platform: str) -> ListingInfo:
    return ListingInfo(
        platform=platform,
        url=("https://item.m.jd.com/product/123.html" if platform == "jd"
             else "https://detail.tmall.com/item.htm?id=456"),
        title="iQOO Neo11 12GB+512GB",
        shop_name="iQOO官方旗舰店",
        shop_type="official_flagship",
        platform_item_id="123" if platform == "jd" else "456",
    )


def test_jd_link_uses_selected_browser_not_app_profile(client, monkeypatch):
    async def extension(platform, url):
        assert platform == "jd"
        assert url == "https://item.jd.com/123.html"
        return _info("jd")

    monkeypatch.setattr("app.api.routes_listings.resolve_with_browser_extension", extension)
    response = client.post("/api/v1/listings/resolve", json={"url": "https://item.jd.com/123.html"})
    assert response.status_code == 200
    assert response.json()["platform_item_id"] == "123"


def test_taobao_link_falls_back_to_selected_browser_after_app_login_failure(
    client, monkeypatch,
):
    client.get("/api/v1/accounts")
    with session_scope() as db:
        account = db.query(Account).filter(Account.platform == "taobao").one()
        account.status = "logged_in"
        db.commit()

    class FailingAdapter:
        async def resolve_listing(self, url, account):
            raise LoginRequired("应用浏览器登录态失效")

    monkeypatch.setattr("app.api.routes_listings.get_adapter", lambda _: FailingAdapter())
    async def extension(platform, url):
        assert platform == "taobao"
        return _info("taobao")

    monkeypatch.setattr("app.api.routes_listings.resolve_with_browser_extension", extension)
    response = client.post(
        "/api/v1/listings/resolve", json={"url": "https://detail.tmall.com/item.htm?id=456"}
    )
    assert response.status_code == 200
    assert response.json()["platform_item_id"] == "456"


@pytest.mark.asyncio
async def test_extension_link_info_validates_jd_identity(monkeypatch):
    async def observe(platform, url, sku_id=None):
        return {
            "url": "https://item.jd.com/999.html", "title": "Other Product",
            "body": "商品详情 京东价 ¥3999 其他信息 " * 10,
        }

    monkeypatch.setattr("app.services.listing_resolution.edge_bridge.observe", observe)
    with pytest.raises(ParseError, match="其他商品"):
        await resolve_with_browser_extension("jd", "https://item.jd.com/123.html")


@pytest.mark.asyncio
async def test_extension_link_info_reads_taobao_shop(monkeypatch):
    async def observe(platform, url, sku_id=None):
        assert platform == "taobao"
        return {
            "url": "https://detail.tmall.com/item.htm?id=456",
            "title": "iQOO Neo11 12GB+512GB",
            "title_texts": [],
            "body": "iQOO Neo11 12GB+512GB 到手价 ¥2999 加入购物车 商品详情 " * 5,
            "price_texts": ["¥2999"],
            "shop_texts": ["iQOO官方旗舰店"],
            "html": "<html></html>",
        }

    monkeypatch.setattr("app.services.listing_resolution.edge_bridge.observe", observe)
    info = await resolve_with_browser_extension(
        "taobao", "https://detail.tmall.com/item.htm?id=456&skuId=789"
    )
    assert info.platform_item_id == "456"
    assert info.platform_sku_id == "789"
    assert info.shop_name == "iQOO官方旗舰店"


@pytest.mark.asyncio
async def test_extension_visits_original_taobao_link(monkeypatch):
    pasted = (
        "https://detail.tmall.com/item.htm?ali_refid=search123"
        "&id=1076349303771&priceTId=12345&skuId=6302158815917"
    )

    async def observe(platform, url, sku_id=None):
        assert url == pasted
        assert sku_id == "6302158815917"
        return {
            "url": pasted,
            "title": "iQOO 手机商品详情",
            "body": "iQOO 手机商品详情 到手价 ¥2999 加入购物车 " * 5,
            "price_texts": ["¥2999"],
            "shop_texts": ["iQOO官方旗舰店"],
            "html": "<html></html>",
        }

    monkeypatch.setattr("app.services.listing_resolution.edge_bridge.observe", observe)
    info = await resolve_with_browser_extension("taobao", pasted)
    assert info.url == pasted
