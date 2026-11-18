import asyncio
import time

import pytest

from app.adapters.base import PriceQuote
from app.core.exceptions import ParseError, RateLimited
from app.core.models import Listing
from app.services.edge_bridge import EdgeBridge


async def test_edge_bridge_claims_one_scheduled_job_and_returns_failure():
    bridge = EdgeBridge()
    bridge.last_seen[("edge", "jd")] = time.monotonic()
    listing = Listing(platform="jd", platform_item_id="123456", platform_sku_id=None)

    fetch = asyncio.create_task(bridge.fetch(listing))
    await asyncio.sleep(0)
    job = bridge.claim()

    assert job is not None
    assert job["platform"] == "jd"
    assert job["kind"] == "product"
    assert job["url"] == "https://item.jd.com/123456.html"
    assert bridge.claim() is None
    assert bridge.submit(job["id"], {"error": "PC 频控"})
    with pytest.raises(RateLimited, match="PC 频控"):
        await fetch
    assert bridge.pending == {}
    assert not bridge.submit(job["id"], {"error": "重复结果"})


async def test_bridge_rejects_removed_search_jobs():
    bridge = EdgeBridge()
    with pytest.raises(ValueError, match="Unsupported browser observation"):
        await bridge.observe("jd", "https://search.jd.com/Search?keyword=Neo11", kind="search")


async def test_edge_bridge_without_extension_never_starts_jd_browser():
    bridge = EdgeBridge()

    class MissingBrowser:
        async def launch(self, browser, bootstrap_token):
            raise FileNotFoundError(f"未找到所选浏览器：{browser}")

    bridge.browser_launcher = MissingBrowser()
    with pytest.raises(RateLimited, match="未找到所选浏览器"):
        await bridge.fetch(Listing(platform="jd", platform_item_id="123456"))
    assert bridge.claim() is None


async def test_offline_extension_starts_selected_browser_and_uses_bootstrap_window():
    bridge = EdgeBridge()
    launches = []

    class ConnectingBrowser:
        async def launch(self, browser, bootstrap_token):
            launches.append((browser, bootstrap_token))
            bridge.claim({"jd", "taobao"}, browser, 2)

    bridge.browser_launcher = ConnectingBrowser()
    listing = Listing(platform="jd", platform_item_id="123456")
    fetch = asyncio.create_task(bridge.fetch(listing))
    await asyncio.sleep(0)
    job = bridge.claim({"jd"}, "edge", 2)

    assert launches and launches[0][0] == "edge"
    assert job is not None
    assert job["isolated_window"] is True
    assert job["bootstrap_token"] == launches[0][1]
    assert bridge.submit(job["id"], {"error": "测试完成"})
    with pytest.raises(RateLimited, match="测试完成"):
        await fetch


async def test_stale_taobao_connection_opens_target_window_when_job_is_not_claimed():
    bridge = EdgeBridge()
    bridge.last_seen[("edge", "taobao")] = time.monotonic()
    bridge.browser_claim_timeout = 0.01
    launches = []

    class WakingBrowser:
        async def launch(self, browser, bootstrap_token):
            launches.append((browser, bootstrap_token))
            job = bridge.claim({"jd", "taobao"}, browser, 2)
            assert job is not None
            assert job["bootstrap_token"] == bootstrap_token
            assert bridge.submit(job["id"], {"error": "唤醒成功"}, browser)

    bridge.browser_launcher = WakingBrowser()
    listing = Listing(
        platform="taobao",
        platform_item_id="1234567890",
        url="https://detail.tmall.com/item.htm?id=1234567890",
    )
    with pytest.raises(RateLimited, match="唤醒成功"):
        await bridge.fetch(listing)
    assert launches == [("edge", launches[0][1])]


async def test_force_new_tab_is_sent_to_selected_extension():
    bridge = EdgeBridge()
    bridge.last_seen[("edge", "taobao")] = time.monotonic()
    task = asyncio.create_task(bridge.observe(
        "taobao", "https://detail.tmall.com/item.htm?id=1234567890",
        force_new_tab=True,
    ))
    await asyncio.sleep(0)
    job = bridge.claim({"taobao"}, "edge")
    assert job is not None
    assert job["force_new_tab"] is True
    assert bridge.submit(job["id"], {"url": job["url"]}, "edge")
    assert (await task)["url"] == job["url"]


async def test_old_extension_cannot_claim_taobao_job():
    bridge = EdgeBridge()
    bridge.last_seen[("edge", "taobao")] = time.monotonic()
    listing = Listing(
        platform="taobao",
        platform_item_id="824950233983",
        platform_sku_id="4403221617613",
        url="https://detail.tmall.com/item.htm?id=824950233983&skuId=4403221617613",
    )
    fetch = asyncio.create_task(bridge.fetch(listing))
    await asyncio.sleep(0)

    assert bridge.claim({"jd"}) is None
    job = bridge.claim({"jd", "taobao"})
    assert job is not None
    assert job["platform"] == "taobao"
    assert job["sku_id"] == "4403221617613"
    assert job["url"] == listing.url
    assert bridge.submit(job["id"], {"error": "测试停止"})
    with pytest.raises(RateLimited, match="测试停止"):
        await fetch


async def test_only_selected_browser_can_claim_and_switch_requeues_active_job():
    bridge = EdgeBridge()
    listing = Listing(platform="jd", platform_item_id="123456", platform_sku_id=None)
    bridge.claim({"jd"}, "edge")
    bridge.claim({"jd"}, "chrome")
    assert bridge.connected("jd")

    fetch = asyncio.create_task(bridge.fetch(listing))
    await asyncio.sleep(0)
    assert bridge.claim({"jd"}, "chrome") is None
    edge_job = bridge.claim({"jd"}, "edge")
    assert edge_job is not None

    bridge.set_browser("chrome")
    assert bridge.selected_browser == "chrome"
    assert bridge.connected("jd")
    assert bridge.connected_browsers() == ["edge", "chrome"]
    assert not bridge.submit(edge_job["id"], {"error": "旧浏览器结果"}, "edge")

    chrome_job = bridge.claim({"jd"}, "chrome")
    assert chrome_job is not None
    assert chrome_job["id"] == edge_job["id"]
    assert bridge.submit(chrome_job["id"], {"error": "新浏览器结果"}, "chrome")
    with pytest.raises(RateLimited, match="新浏览器结果"):
        await fetch


def test_selected_browser_status_ignores_other_browser_heartbeat():
    bridge = EdgeBridge()
    bridge.claim({"jd", "taobao"}, "edge")
    bridge.set_browser("firefox")
    assert not bridge.connected("jd")
    assert bridge.connected_browsers() == ["edge"]
    bridge.claim({"jd"}, "firefox")
    assert bridge.connected("jd")
    assert not bridge.connected("taobao")


@pytest.mark.parametrize("first_result", ["parse_error", "low", "exception"])
async def test_taobao_reused_tab_failure_opens_one_fresh_tab(monkeypatch, first_result):
    bridge = EdgeBridge()
    listing = Listing(
        id=8, platform="taobao", platform_item_id="1234567890",
        platform_sku_id="987654321",
        url="https://detail.tmall.com/item.htm?id=1234567890&skuId=987654321",
    )
    requests = []

    async def observe(platform, url, sku_id=None, kind="product", force_new_tab=False):
        requests.append((platform, url, sku_id, force_new_tab))
        return {"url": url, "reused_tab": not force_new_tab, "fresh": force_new_tab}

    def parse(_listing, observation):
        if not observation["fresh"]:
            if first_result == "exception":
                raise ParseError("旧标签解析失败")
            return PriceQuote(
                "taobao", 8, "page", 0 if first_result == "parse_error" else 269900,
                status="parse_error" if first_result == "parse_error" else "ok",
                confidence="low",
            )
        return PriceQuote("taobao", 8, "page", 220379, status="ok", confidence="high")

    monkeypatch.setattr(bridge, "observe", observe)
    monkeypatch.setattr(bridge, "_quote_from_observation", parse)
    quote = await bridge.fetch(listing)
    assert quote.effective_price_cents == 220379
    assert [item[3] for item in requests] == [False, True]


async def test_taobao_fresh_tab_failure_is_not_retried(monkeypatch):
    bridge = EdgeBridge()
    listing = Listing(
        id=8, platform="taobao", platform_item_id="1234567890",
        url="https://detail.tmall.com/item.htm?id=1234567890",
    )
    calls = []

    async def observe(platform, url, sku_id=None, kind="product", force_new_tab=False):
        calls.append(force_new_tab)
        return {"url": url, "reused_tab": False}

    def parse(_listing, _observation):
        raise ParseError("新页面仍异常")

    monkeypatch.setattr(bridge, "observe", observe)
    monkeypatch.setattr(bridge, "_quote_from_observation", parse)
    with pytest.raises(ParseError, match="新页面仍异常"):
        await bridge.fetch(listing)
    assert calls == [False]
