import asyncio
import json

import pytest

from app.core.exceptions import RateLimited
from app.services.edge_bridge import EdgeBridge, JdVisitPacer


async def test_jd_visits_are_serial_and_use_a_new_random_gap_each_time():
    now = [100.0]
    delays = []
    draws = iter((30.0, 47.0, 60.0))

    async def sleep(seconds):
        delays.append(seconds)
        now[0] += seconds

    async def visit():
        return {"visited_at": now[0]}

    pacer = JdVisitPacer(
        clock=lambda: now[0], sleep=sleep,
        uniform=lambda low, high: next(draws),
    )
    observed = [await pacer.run(visit) for _ in range(3)]
    assert [item["visited_at"] for item in observed] == [100.0, 130.0, 177.0]
    assert delays == [30.0, 47.0]
    assert pacer.next_allowed == 237.0


async def test_jd_gap_survives_restart(tmp_path):
    state_file = tmp_path / "jd-pc-visit.json"
    now = [100.0]
    wall = [1000.0]
    first = JdVisitPacer(
        clock=lambda: now[0], wall_clock=lambda: wall[0],
        uniform=lambda low, high: 45.0,
    )
    first.configure(state_file)
    await first.run(lambda: asyncio.sleep(0, result={}))

    now[0] = 200.0
    wall[0] = 1020.0
    delays = []

    async def sleep(seconds):
        delays.append(seconds)
        now[0] += seconds
        wall[0] += seconds

    restarted = JdVisitPacer(
        clock=lambda: now[0], wall_clock=lambda: wall[0], sleep=sleep,
        uniform=lambda low, high: 30.0,
    )
    restarted.configure(state_file)
    await restarted.run(lambda: asyncio.sleep(0, result={}))
    assert delays == [25.0]


async def test_cancelled_jd_wait_does_not_start_another_page():
    now = [100.0]
    waiting = asyncio.Event()
    visits = []

    async def sleep(_seconds):
        waiting.set()
        await asyncio.Future()

    async def visit():
        visits.append(now[0])
        return {}

    pacer = JdVisitPacer(
        clock=lambda: now[0], sleep=sleep,
        uniform=lambda low, high: 30.0,
    )
    await pacer.run(visit)
    second = asyncio.create_task(pacer.run(visit))
    await waiting.wait()
    second.cancel()
    with pytest.raises(asyncio.CancelledError):
        await second
    assert visits == [100.0]
    assert pacer.next_allowed == 130.0


async def test_jd_frequency_response_warns_but_allows_next_visit(tmp_path):
    now = [100.0]
    wall = [1000.0]
    state_file = tmp_path / "jd-pc-visit.json"

    async def sleep(seconds):
        now[0] += seconds
        wall[0] += seconds

    pacer = JdVisitPacer(
        clock=lambda: now[0], wall_clock=lambda: wall[0], sleep=sleep,
        uniform=lambda low, high: 30.0,
    )
    pacer.configure(state_file)
    await pacer.run(lambda: asyncio.sleep(0, result={
        "url": "https://pc-frequent-pro.pf.jd.com/?reason=403",
    }))
    assert pacer.frequency_warning is True
    assert json.loads(state_file.read_text(encoding="utf-8"))["frequency_warning"] is True
    await pacer.run(lambda: asyncio.sleep(0, result={
        "url": "https://item.jd.com/123456.html",
    }))
    assert now[0] == 130.0
    assert pacer.frequency_warning is False


async def test_old_cooldown_record_becomes_warning_without_blocking(tmp_path):
    state_file = tmp_path / "jd-pc-visit.json"
    state_file.write_text(json.dumps({"blocked_until_at": 1070.0}), encoding="utf-8")
    pacer = JdVisitPacer(clock=lambda: 100.0, wall_clock=lambda: 1000.0)
    pacer.configure(state_file)
    assert pacer.frequency_warning is True
    await pacer.run(lambda: asyncio.sleep(0, result={
        "url": "https://item.jd.com/123456.html",
    }))
    assert pacer.frequency_warning is False
    restarted = JdVisitPacer(clock=lambda: 110.0, wall_clock=lambda: 1010.0)
    restarted.configure(state_file)
    assert restarted.frequency_warning is False


async def test_jd_product_visits_use_the_pacer():
    bridge = EdgeBridge()
    draws = []

    def uniform(low, high):
        draws.append((low, high))
        return 0.0

    bridge.jd_pacer = JdVisitPacer((0.0, 0.0), uniform=uniform)
    bridge.claim({"jd"}, "edge", 2)
    task = asyncio.create_task(bridge.observe("jd", "https://item.jd.com/123456.html"))
    await asyncio.sleep(0)
    job = bridge.claim({"jd"}, "edge", 2)
    assert job is not None and job["kind"] == "product"
    assert bridge.submit(job["id"], {"error": "测试停止"}, "edge")
    with pytest.raises(RateLimited, match="测试停止"):
        await task
    assert draws == [(0.0, 0.0)]
