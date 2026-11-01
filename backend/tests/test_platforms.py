from app.core.platforms import detect_platform, platform_label


def test_detect_platform():
    assert detect_platform("https://item.jd.com/100.html") == "jd"
    assert detect_platform("https://item.m.jd.com/product/100.html") == "jd"
    assert detect_platform("https://u.jd.com/abc") == "jd"
    assert detect_platform("https://detail.tmall.com/item.htm?id=1") == "taobao"
    assert detect_platform("https://item.taobao.com/item.htm?id=1") == "taobao"
    assert detect_platform("https://m.tb.cn/h.abcd") == "taobao"
    assert detect_platform("https://example.com/item") is None
    assert detect_platform("not-a-url") is None


def test_platform_label():
    assert platform_label("jd") == "京东"
    assert platform_label("taobao") == "淘宝"
    assert platform_label("other") == "other"
