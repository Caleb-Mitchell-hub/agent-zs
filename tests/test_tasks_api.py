"""任务 API 集成测试（httpx ASGITransport + 真实 DB，user_id=1 隔离清理）"""
import pytest
import pytest_asyncio
import httpx
from datetime import datetime

from app.main import app

TEST_USER = 1


@pytest_asyncio.fixture(autouse=True)
async def _db():
    from app.db.session import init_db, close_db
    from app.tasks.service import _execute_write
    await init_db()
    for sql in (
        "DELETE FROM user_tasks WHERE user_id = :uid",
        "DELETE FROM task_schedules WHERE user_id = :uid",
        "DELETE FROM leaves WHERE user_id = :uid",
    ):
        await _execute_write(sql, {"uid": TEST_USER})
    yield
    for sql in (
        "DELETE FROM user_tasks WHERE user_id = :uid",
        "DELETE FROM task_schedules WHERE user_id = :uid",
        "DELETE FROM leaves WHERE user_id = :uid",
    ):
        await _execute_write(sql, {"uid": TEST_USER})
    await close_db()


@pytest_asyncio.fixture
async def ac(_db):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.mark.asyncio
async def test_create_and_list_task(ac, auth_headers):
    r = await ac.post("/api/v1/tasks", json={"title": "API测试任务"}, headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    task_id = r.json()["task_id"]
    r2 = await ac.get("/api/v1/tasks", headers=auth_headers)
    assert r2.status_code == 200
    assert any(t["task_id"] == task_id for t in r2.json()["tasks"])


@pytest.mark.asyncio
async def test_update_and_delete_task(ac, auth_headers):
    r = await ac.post("/api/v1/tasks", json={"title": "待完成"}, headers=auth_headers)
    task_id = r.json()["task_id"]

    r2 = await ac.patch(f"/api/v1/tasks/{task_id}", json={"status": "done"}, headers=auth_headers)
    assert r2.status_code == 200
    assert r2.json()["task"]["status"] == "done"

    r3 = await ac.delete(f"/api/v1/tasks/{task_id}", headers=auth_headers)
    assert r3.status_code == 200
    assert r3.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_worklog_endpoint(ac, auth_headers):
    r = await ac.get("/api/v1/tasks/worklog", params={"year": 2026, "month": 8}, headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert "total_done" in data and "rate" in data


@pytest.mark.asyncio
async def test_schedule_create_and_delete(ac, auth_headers):
    r = await ac.post("/api/v1/tasks", json={"title": "定时提醒任务"}, headers=auth_headers)
    task_id = r.json()["task_id"]

    trigger = datetime(2099, 1, 1, 9, 0).isoformat()
    r2 = await ac.post(
        f"/api/v1/tasks/{task_id}/schedule",
        json={"trigger_time": trigger, "action": "remind"},
        headers=auth_headers,
    )
    assert r2.status_code == 200
    assert r2.json()["schedule_id"] > 0

    r3 = await ac.delete(f"/api/v1/tasks/{task_id}/schedule", headers=auth_headers)
    assert r3.status_code == 200
    assert r3.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_schedule_delete_not_found(ac, auth_headers):
    r = await ac.post("/api/v1/tasks", json={"title": "无定时任务"}, headers=auth_headers)
    task_id = r.json()["task_id"]
    r2 = await ac.delete(f"/api/v1/tasks/{task_id}/schedule", headers=auth_headers)
    assert r2.status_code == 404


@pytest.mark.asyncio
async def test_leaves_create_and_list(ac, auth_headers):
    r = await ac.post(
        "/api/v1/tasks/leaves",
        json={"day": "2026-08-14", "note": "年假"},
        headers=auth_headers,
    )
    assert r.status_code == 200
    assert r.json()["leave_id"] > 0

    r2 = await ac.get("/api/v1/tasks/leaves", headers=auth_headers)
    assert r2.status_code == 200
    assert any(l["day"] == "2026-08-14" for l in r2.json()["leaves"])


@pytest.mark.asyncio
async def test_worklog_day_endpoint(ac, auth_headers):
    from app.tasks.service import get_task

    r = await ac.post("/api/v1/tasks", json={"title": "今日完成"}, headers=auth_headers)
    task_id = r.json()["task_id"]
    await ac.patch(f"/api/v1/tasks/{task_id}", json={"status": "done"}, headers=auth_headers)

    row = await get_task(TEST_USER, task_id)
    day = row["completed_at"].strftime("%Y-%m-%d")
    r2 = await ac.get("/api/v1/tasks/worklog/day", params={"date": day}, headers=auth_headers)
    assert r2.status_code == 200
    data = r2.json()
    assert "done_tasks" in data and "created_tasks" in data
    assert any(d["task_id"] == task_id for d in data["done_tasks"])
