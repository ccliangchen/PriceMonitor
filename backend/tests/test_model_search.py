from app.adapters.base import ListingInfo
from app.adapters.taobao.parser import (
    TaobaoSearchItem,
    TaobaoSkuVariant,
    TaobaoStoreLink,
)
from app.core.product_query import parse_product_query
from app.services import model_search as search_service
from app.services.model_search import (
    SearchSku,
    _sku_options,
    _taobao_title_matches,
)


def _sku(
    *,
    ram: int,
    storage: int,
    color: str = "",
    spec: str = "官方标配",
    sku_id: str = "",
) -> SearchSku:
    return SearchSku(
        color=color,
        spec=spec,
        sku_id=sku_id or f"{ram}-{storage}-{color}",
        url=f"https://detail.tmall.com/item.htm?id=1&skuId={sku_id or ram}",
        ram_gb=ram,
        storage_gb=storage,
    )


def test_taobao_title_matching_ignores_spaces_and_requires_variant():
    query = parse_product_query("iQOO Neo11 至尊版 12G+512G")

    assert _taobao_title_matches(
        "【立享15%国家补贴】iQOO Neo11 至尊版新品手机", query
    )
    assert _taobao_title_matches("vivo iQOO Neo11 至尊版 12GB+512GB", query)
    assert not _taobao_title_matches("iQOO Neo11 12GB+512GB", query)
    assert not _taobao_title_matches("iQOO Neo12 至尊版 12GB+512GB", query)


def test_sku_options_prefer_standard_package_and_dedupe_specs():
    variants = [
        _sku(ram=12, storage=512, color="乘风", sku_id="a"),
        _sku(ram=12, storage=512, color="疾影黑", sku_id="b"),
        _sku(ram=16, storage=256, color="乘风", sku_id="c"),
        _sku(ram=12, storage=512, color="礼盒", spec="礼盒装", sku_id="d"),
    ]

    options = _sku_options(variants)

    assert [(item.ram_gb, item.storage_gb) for item in options] == [
        (12, 512),
        (16, 256),
    ]
    assert all(item.spec == "官方标配" for item in options)


def test_sku_options_fall_back_when_standard_package_is_absent():
    variants = [
        _sku(ram=12, storage=512, spec="套餐一", sku_id="a"),
        _sku(ram=16, storage=256, spec="套餐二", sku_id="b"),
    ]

    options = _sku_options(variants)

    assert len(options) == 2
    assert {item.spec for item in options} == {"套餐一", "套餐二"}


class FakeTaobaoAdapter:
    def __init__(self) -> None:
        self.store = TaobaoStoreLink(
            name="iQOO手机官方旗舰店",
            url="https://shop71799145.taobao.com/category.htm",
        )
        self.item = TaobaoSearchItem(
            item_id="1064830909687",
            title="iQOO Neo11 至尊版 12GB+512GB",
            url="https://detail.tmall.com/item.htm?id=1064830909687",
        )

    async def find_official_store(self, brand, account, keyword=""):
        assert brand == "iQOO"
        assert "Neo11" in keyword
        return self.store

    async def search_store_items(self, store, keyword, account):
        assert store == self.store
        assert "Neo11" in keyword
        return [self.item]

    async def resolve_listing_with_skus(self, url, account):
        info = ListingInfo(
            platform="taobao",
            url=url,
            title=self.item.title,
            shop_name=self.store.name,
            shop_type="official_flagship",
            platform_item_id=self.item.item_id,
            evidence={"official_badge": "true", "badge_text": "官方旗舰店"},
        )
        variants = [
            TaobaoSkuVariant(
                color="乘风",
                spec="官方标配",
                sku_id="6316034474209",
                url=url + "&skuId=6316034474209",
                ram_gb=12,
                storage_gb=512,
            )
        ]
        return info, variants


async def test_taobao_search_flow_returns_platform_and_sku(monkeypatch):
    adapter = FakeTaobaoAdapter()
    monkeypatch.setattr(search_service, "get_adapter", lambda platform: adapter)

    result = await search_service.search_model(
        "iQOO Neo11 至尊版 12G+512G",
        "taobao",
        object(),
    )

    assert result["query"]["brand"] == "iQOO"
    candidate = result["candidates"][0]
    assert candidate["platform"] == "taobao"
    assert candidate["store_name"] == "iQOO手机官方旗舰店"
    assert candidate["platform_item_id"] == "1064830909687"
    assert candidate["requested_available"] is True
    assert candidate["matched_sku_id"] == "6316034474209"
    assert candidate["variants"][0]["ram_gb"] == 12
    assert candidate["variants"][0]["storage_gb"] == 512
    assert candidate["shop_evidence"]["official_badge"] == "true"
