"""任务 CRUD service 集成测试（连真实库，专用 user_id 隔离 + 清理）"""
import pytest
import pytest_asyncio
from datetime import datetime
from app.tasks.service import (
    create_task, list_tasks, update_task, delete_task, get_task,
)

TEST_USER = 900001


@pytest_asyncio.fixture(autouse=True)
async def _db():
    """每个测试独立初始化数据库、清理残留/本次数据、关闭连接池。

    function 级作用域，避免 async fixture 跨 event-loop 导致 aiomysql 连接失效。
    """
    from app.db.session import init_db, close_db
    from app.tasks.service import _execute_write
    await init_db()
    # 测试前清理残留，测试后清理本次数据，最后关闭连接池
    await _execute_write("DELETE FROM user_tasks WHERE user_id = :uid", {"uid": TEST_USER})
    yield
    await _execute_write("DELETE FROM user_tasks WHERE user_id = :uid", {"uid": TEST_USER})
    await close_db()


@pytest.mark.asyncio
async def test_create_and_get_task():
    task = await create_task(TEST_USER, "测试任务A", deadline=datetime(2026, 8, 20, 10, 0))
    assert task["task_id"] > 0
    row = await get_task(TEST_USER, task["task_id"])
    assert row["title"] == "测试任务A"
    assert row["status"] == "pending"


@pytest.mark.asyncio
async def test_list_filter_by_status():
    t1 = await create_task(TEST_USER, "任务1")
    await create_task(TEST_USER, "任务2")
    await update_task(TEST_USER, t1["task_id"], status="done")
    done = await list_tasks(TEST_USER, filter="done")
    assert all(r["status"] == "done" for r in done)
    assert len(done) == 1


@pytest.mark.asyncio
async def test_update_done_sets_completed_at():
    task = await create_task(TEST_USER, "任务X")
    await update_task(TEST_USER, task["task_id"], status="done")
    row = await get_task(TEST_USER, task["task_id"])
    assert row["completed_at"] is not None


@pytest.mark.asyncio
async def test_delete_task():
    task = await create_task(TEST_USER, "待删任务")
    ok = await delete_task(TEST_USER, task["task_id"])
    assert ok is True
    assert await get_task(TEST_USER, task["task_id"]) is None


@pytest.mark.asyncio
async def test_isolated_by_user():
    task = await create_task(TEST_USER, "隔离任务")
    assert await get_task(TEST_USER + 1, task["task_id"]) is None
