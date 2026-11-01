from app.core.product_query import parse_product_query, suggest_fields_from_title


def test_suggest_fields_from_taobao_title():
    fields = suggest_fields_from_title(
        "【赠充电宝】vivo iQOO Neo12新品2K 185Hz屏幕大电池高通学生游戏手机"
        "iQOO官方旗舰店官网正品iqooneo12国补"
    )

    assert fields["brand"] == "iQOO"
    assert fields["model"] == "Neo12"


def test_suggest_fields_from_title_with_variant():
    fields = suggest_fields_from_title(
        "vivo iQOO Neo11 至尊版 12GB+512GB 官方旗舰店"
    )

    assert fields["brand"] == "iQOO"
    assert fields["model"] == "Neo11"
    assert fields["variant"] == "至尊版"


def test_chipset_snapdragon_does_not_become_variant():
    fields = suggest_fields_from_title(
        "iQOO Neo12 第五代骁龙8至尊版 12GB+512GB 官方旗舰店"
    )

    assert fields["model"] == "Neo12"
    assert fields["variant"] == ""


def test_suggest_fields_for_iphone():
    fields = suggest_fields_from_title("Apple iPhone 17 Pro 256GB")

    assert fields["brand"] == "Apple"
    assert fields["model"] == "iPhone 17"
    assert fields["variant"] == "Pro"


def test_parse_compact_iqoo_query():
    query = parse_product_query("IQOO neo11至尊版12G+512G")

    assert query.brand == "iQOO"
    assert query.model == "Neo11"
    assert query.variant == "至尊版"
    assert query.ram_gb == 12
    assert query.storage_gb == 512


def test_parse_spaced_gb_query():
    query = parse_product_query("iQOO Neo11 至尊版 12GB+512GB")

    assert query.brand == "iQOO"
    assert query.model == "Neo11"
    assert query.variant == "至尊版"
    assert (query.ram_gb, query.storage_gb) == (12, 512)


def test_parse_plain_plus_query():
    query = parse_product_query("小米15 12+256")

    assert query.brand == "小米"
    assert query.model == "15"
    assert query.ram_gb == 12
    assert query.storage_gb == 256


def test_parse_space_specs_query():
    query = parse_product_query("vivo X200 Pro 16GB 512GB")

    assert query.brand == "vivo"
    assert query.model == "X200"
    assert query.variant == "Pro"
    assert (query.ram_gb, query.storage_gb) == (16, 512)


def test_missing_specs_is_allowed_but_none():
    query = parse_product_query("iQOO Neo11 至尊版")

    assert query.brand == "iQOO"
    assert query.ram_gb is None
    assert query.storage_gb is None
