from sqlalchemy import select

from app.adapters.base import ListingInfo
from app.core.db import session_scope
from app.core.models import Account


def test_account_list_creates_jd_account(client):
    response = client.get("/api/v1/accounts")

    assert response.status_code == 200
    accounts = response.json()
    assert len(accounts) == 1
    assert accounts[0]["platform"] == "jd"
    assert accounts[0]["status"] == "needs_login"


def test_resolve_requires_login(client):
    response = client.post(
        "/api/v1/listings/resolve",
        json={"url": "https://item.jd.com/100.html"},
    )

    assert response.status_code == 409
    assert "登录" in response.json()["detail"]


def test_resolve_with_fake_adapter(client, monkeypatch):
    client.get("/api/v1/accounts")
    with session_scope() as db:
        account = db.scalars(select(Account)).first()
        assert account is not None
        account.status = "logged_in"
        db.commit()

    class FakeAdapter:
        async def resolve_listing(self, url, account):
            return ListingInfo(
                platform="jd",
                url=url,
                title="iQOO Neo11 至尊版 12GB+512GB",
                shop_name="iQOO京东自营旗舰店",
                shop_type="jd_official_self",
                platform_item_id="100",
                evidence={"self_operated": "true", "shop_brand": "iQOO"},
            )

    monkeypatch.setattr(
        "app.api.routes_listings.get_adapter",
        lambda platform: FakeAdapter(),
    )

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
