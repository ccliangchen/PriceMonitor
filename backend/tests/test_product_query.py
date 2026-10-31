from app.core.product_query import parse_product_query


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
