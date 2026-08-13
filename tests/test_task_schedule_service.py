"""定时任务 + 请假 + 工作记录聚合 service 集成测试（连真实库，专用 user_id 隔离 + 清理）"""
import pytest
import pytest_asyncio
from datetime import datetime, date
from app.tasks.service import (
    create_task, create_schedule, delete_schedule, list_pending_schedules,
    mark_schedule_fired, advance_task, get_task,
    create_leave, list_leaves, delete_leave, get_worklog, get_workday_sets,
    get_worklog_day, _execute_write,
)

TEST_USER = 900001


@pytest_asyncio.fixture(autouse=True)
async def _db():
    """每个测试独立初始化数据库、清理三张表、关闭连接池。

    function 级作用域，避免 async fixture 跨 event-loop 导致 aiomysql 连接失效。
    """
    from app.db.session import init_db, close_db
    from app.tasks.service import _execute_write
    await init_db()
    # 测试前清理残留，测试后清理本次数据，最后关闭连接池
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


@pytest.mark.asyncio
async def test_create_schedule():
    task = await create_task(TEST_USER, "带提醒任务")
    sched = await create_schedule(TEST_USER, task["task_id"], datetime(2026, 8, 20, 9, 0), "remind")
    assert sched["schedule_id"] > 0
    pending = await list_pending_schedules()
    assert any(
        s["task_id"] == task["task_id"] and s["fired"] == 0 and s["title"] == "带提醒任务"
        for s in pending
    )


@pytest.mark.asyncio
async def test_delete_schedule():
    task = await create_task(TEST_USER, "待删定时任务")
    sched = await create_schedule(TEST_USER, task["task_id"], datetime(2026, 8, 20, 9, 0), "remind")
    ok = await delete_schedule(TEST_USER, task["task_id"])
    assert ok is True
    pending = await list_pending_schedules()
    assert all(s["schedule_id"] != sched["schedule_id"] for s in pending)


@pytest.mark.asyncio
async def test_mark_fired_and_advance():
    task = await create_task(TEST_USER, "自动推进任务")
    sched = await create_schedule(TEST_USER, task["task_id"], datetime(2026, 8, 20, 9, 0), "remind_advance", "done")
    await mark_schedule_fired(sched["schedule_id"])
    await advance_task(task["task_id"], "done")
    row = await get_task(TEST_USER, task["task_id"])
    assert row["status"] == "done"
    assert row["completed_at"] is not None


@pytest.mark.asyncio
async def test_leave_crud():
    leave = await create_leave(TEST_USER, date(2026, 8, 14), "年假")
    assert leave["leave_id"] > 0
    leaves = await list_leaves(TEST_USER)
    assert any(l["day"] == date(2026, 8, 14) for l in leaves)
    ok = await delete_leave(TEST_USER, leave["leave_id"])
    assert ok is True
    assert await list_leaves(TEST_USER) == []


@pytest.mark.asyncio
async def test_get_workday_sets():
    await create_leave(TEST_USER, date(2026, 8, 14), "年假")
    holidays, workdays, leaves = await get_workday_sets(TEST_USER, 2026)
    assert isinstance(holidays, set)
    assert isinstance(workdays, set)
    assert isinstance(leaves, set)
    assert date(2026, 8, 14) in leaves


@pytest.mark.asyncio
async def test_worklog_aggregation():
    t1 = await create_task(TEST_USER, "已完成任务")
    await advance_task(t1["task_id"], "done")
    await create_task(TEST_USER, "待办任务")
    log = await get_worklog(TEST_USER, 2026, 8)
    assert log["total_done"] >= 1
    assert log["total_created"] >= 2
    assert 0 <= log["rate"] <= 1
    assert log["active_days"] >= 1


@pytest.mark.asyncio
async def test_worklog_day():
    t1 = await create_task(TEST_USER, "今日完成")
    await advance_task(t1["task_id"], "done")
    row = await get_task(TEST_USER, t1["task_id"])
    day = row["created_at"].strftime("%Y-%m-%d")
    detail = await get_worklog_day(TEST_USER, day)
    assert any(d["task_id"] == t1["task_id"] for d in detail["done_tasks"])
    assert any(c["task_id"] == t1["task_id"] for c in detail["created_tasks"])


@pytest.mark.asyncio
async def test_worklog_cross_month_strict_boundary():
    # 上月创建、本月完成的任务：计入 total_done，不计入 total_created
    await _execute_write(
        "INSERT INTO user_tasks (user_id, title, status, created_at, completed_at) "
        "VALUES (:uid, :title, 'done', :created, :completed)",
        {
            "uid": TEST_USER,
            "title": "跨月完成",
            "created": "2026-07-20 10:00:00",
            "completed": "2026-08-10 10:00:00",
        },
    )
    log = await get_worklog(TEST_USER, 2026, 8)
    assert log["total_done"] == 1
    assert log["total_created"] == 0
