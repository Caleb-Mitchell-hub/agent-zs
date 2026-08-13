"""调度器单元测试（不真正起 APScheduler，验证 pub/sub 与 _fire 逻辑）"""
import asyncio
import pytest
from datetime import datetime
from app.tasks import scheduler as sched_mod


@pytest.mark.asyncio
async def test_subscribe_and_notify(monkeypatch):
    ts = sched_mod.TaskScheduler()
    q = await ts.subscribe(1)
    await ts._notify(1, {"type": "task_remind", "message": "测试提醒"})
    event = await asyncio.wait_for(q.get(), timeout=1)
    assert event["type"] == "task_remind"
    ts.unsubscribe(1, q)


@pytest.mark.asyncio
async def test_fire_marks_and_advances(monkeypatch):
    """_fire 触发：标记已触发 + 自动推进 + 推送提醒"""
    calls = {}
    async def fake_mark(sid): calls["mark"] = sid
    async def fake_advance(tid, status): calls["advance"] = (tid, status)
    monkeypatch.setattr(sched_mod, "mark_schedule_fired", fake_mark)
    monkeypatch.setattr(sched_mod, "advance_task", fake_advance)

    ts = sched_mod.TaskScheduler()
    q = await ts.subscribe(1)
    sched = {"schedule_id": 5, "task_id": 9, "user_id": 1,
             "action": "remind_advance", "advance_to": "done", "title": "任务A"}
    await ts._fire(sched)

    assert calls["mark"] == 5
    assert calls["advance"] == (9, "done")
    event = await asyncio.wait_for(q.get(), timeout=1)
    assert "任务A" in event["message"]
    ts.unsubscribe(1, q)
