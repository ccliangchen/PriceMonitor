from sqlalchemy import select

from app.adapters.base import ListingInfo
from app.core.db import session_scope
from app.core.exceptions import RateLimited
from app.core.models import Account


def test_account_list_creates_platform_accounts(client):
    response = client.get("/api/v1/accounts")

    assert response.status_code == 200
    accounts = response.json()
    assert [item["platform"] for item in accounts] == ["jd", "taobao"]
    assert all(item["status"] == "needs_login" for item in accounts)


def test_jd_resolve_reports_extension_that_did_not_connect_after_start(client, monkeypatch):
    async def unavailable(*_args):
        raise RateLimited("已启动所选浏览器，但京东采价扩展未连接")

    monkeypatch.setattr("app.api.routes_listings.resolve_with_browser_extension", unavailable)
    response = client.post(
        "/api/v1/listings/resolve",
        json={"url": "https://item.jd.com/100.html"},
    )

    assert response.status_code == 409
    assert "已启动所选浏览器" in response.json()["detail"]


def test_resolve_taobao_url_uses_taobao_account(client, monkeypatch):
    async def unavailable(*_args):
        raise RateLimited("已启动所选浏览器，但淘宝采价扩展未连接")

    monkeypatch.setattr("app.api.routes_listings.resolve_with_browser_extension", unavailable)
    response = client.post(
        "/api/v1/listings/resolve",
        json={"url": "https://detail.tmall.com/item.htm?id=100"},
    )

    assert response.status_code == 409
    assert "淘宝" in response.json()["detail"]


def test_resolve_rejects_unknown_platform(client):
    response = client.post(
        "/api/v1/listings/resolve",
        json={"url": "https://example.com/item.htm?id=100"},
    )

    assert response.status_code == 422


def test_resolve_taobao_with_fake_adapter(client, monkeypatch):
    client.get("/api/v1/accounts")
    with session_scope() as db:
        account = db.scalars(
            select(Account).where(Account.platform == "taobao")
        ).first()
        assert account is not None
        account.status = "logged_in"
        db.commit()

    class FakeAdapter:
        async def resolve_listing(self, url, account):
            return ListingInfo(
                platform="taobao",
                url=url,
                title="iQOO Neo11 12GB+256GB",
                shop_name="iQOO手机官方旗舰店",
                shop_type="official_flagship",
                platform_item_id="824950233983",
                platform_sku_id="4403221617613",
                evidence={"official_badge": "true", "shop_brand": "iQOO"},
            )

    monkeypatch.setattr(
        "app.api.routes_listings.get_adapter",
        lambda platform: FakeAdapter(),
    )

    response = client.post(
        "/api/v1/listings/resolve",
        json={"url": "https://detail.tmall.com/item.htm?id=824950233983"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["platform"] == "taobao"
    assert payload["shop_type"] == "official_flagship"
    assert payload["decision"] == "allowed"
    assert payload["platform_sku_id"] == "4403221617613"


def test_jd_resolve_with_extension_metadata(client, monkeypatch):
    async def fake_extension(platform, url):
        return ListingInfo(
            platform="jd",
            url=url,
            title="iQOO Neo11 至尊版 12GB+512GB",
            shop_name="iQOO京东自营旗舰店",
            shop_type="jd_official_self",
            platform_item_id="100",
            evidence={"self_operated": "true", "shop_brand": "iQOO"},
        )

    monkeypatch.setattr("app.api.routes_listings.resolve_with_browser_extension", fake_extension)

    response = client.post(
        "/api/v1/listings/resolve",
        json={"url": "https://item.jd.com/100.html"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["platform"] == "jd"
    assert payload["shop_type"] == "jd_official_self"
    assert payload["decision"] == "allowed"
    assert payload["detected_specs"] == {}
