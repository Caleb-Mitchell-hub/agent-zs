"""任务管理器 service — 任务 CRUD / 定时任务 / 请假 / 工作记录聚合

遵循 session_service 模式：模块级 _execute_read/_execute_write，原生 SQL。
"""
import calendar
import logging
from datetime import datetime
from sqlalchemy import text

logger = logging.getLogger(__name__)


def _get_factory():
    from app.db.session import async_session_factory
    if async_session_factory is None:
        raise RuntimeError("数据库未初始化")
    return async_session_factory


async def _execute_write(sql: str, params: dict = None) -> int:
    factory = _get_factory()
    async with factory() as session:
        result = await session.execute(text(sql), params or {})
        await session.commit()
        return result.rowcount


async def _execute_read(sql: str, params: dict = None) -> list[dict]:
    factory = _get_factory()
    async with factory() as session:
        result = await session.execute(text(sql), params or {})
        rows = result.mappings().all()
        return [dict(row) for row in rows]


async def create_task(user_id: int, title: str, deadline=None, priority: int = 0, parent_id=None) -> dict:
    """创建任务，返回含 task_id 的 dict。"""
    factory = _get_factory()
    async with factory() as session:
        await session.execute(
            text("""
                INSERT INTO user_tasks (user_id, title, status, priority, deadline, parent_id, created_at)
                VALUES (:uid, :title, 'pending', :priority, :deadline, :parent_id, NOW())
            """),
            {"uid": user_id, "title": title, "priority": priority, "deadline": deadline, "parent_id": parent_id},
        )
        row = (await session.execute(text("SELECT LAST_INSERT_ID() AS task_id"))).mappings().one()
        await session.commit()
    return {"task_id": row["task_id"]}


async def get_task(user_id: int, task_id: int) -> dict | None:
    rows = await _execute_read(
        "SELECT * FROM user_tasks WHERE task_id = :tid AND user_id = :uid",
        {"tid": task_id, "uid": user_id},
    )
    return rows[0] if rows else None


_FILTER_SQL = {
    "all": "",
    "done": "AND status = 'done'",
    "pending": "AND status = 'pending'",
    "doing": "AND status = 'doing'",
}


async def list_tasks(user_id: int, filter: str = "all", q: str = "") -> list[dict]:
    """任务列表（4 过滤 + 关键词），附派生 overdue 标记。"""
    cond = _FILTER_SQL.get(filter, "")
    like = f"%{q}%" if q else None
    sql = f"""
        SELECT task_id, title, status, priority, deadline, parent_id, created_at, completed_at,
               (deadline IS NOT NULL AND deadline < NOW() AND status != 'done') AS overdue
        FROM user_tasks
        WHERE user_id = :uid {cond}
    """
    params = {"uid": user_id}
    if like:
        sql += " AND title LIKE :like"
        params["like"] = like
    sql += " ORDER BY COALESCE(deadline, '9999-12-31') ASC, created_at DESC"
    rows = await _execute_read(sql, params)
    for r in rows:
        r["overdue"] = bool(r.get("overdue"))
    return rows


async def update_task(user_id: int, task_id: int, **fields) -> dict | None:
    """更新任务；status=done 时写 completed_at，否则清空。"""
    sets = []
    params = {"tid": task_id, "uid": user_id}
    for k in ("title", "priority", "deadline"):
        if k in fields and fields[k] is not None:
            sets.append(f"{k} = :{k}")
            params[k] = fields[k]
    if "status" in fields and fields["status"] is not None:
        sets.append("status = :status")
        params["status"] = fields["status"]
        if fields["status"] == "done":
            sets.append("completed_at = NOW()")
        else:
            sets.append("completed_at = NULL")
    if not sets:
        return await get_task(user_id, task_id)
    await _execute_write(
        f"UPDATE user_tasks SET {', '.join(sets)} WHERE task_id = :tid AND user_id = :uid",
        params,
    )
    return await get_task(user_id, task_id)


async def delete_task(user_id: int, task_id: int) -> bool:
    affected = await _execute_write(
        "DELETE FROM user_tasks WHERE task_id = :tid AND user_id = :uid",
        {"tid": task_id, "uid": user_id},
    )
    return affected > 0


# ─────────────── 定时任务 ───────────────

async def create_schedule(user_id: int, task_id: int, trigger_time, action: str, advance_to=None) -> dict:
    """创建定时任务，返回含 schedule_id 的 dict。"""
    factory = _get_factory()
    async with factory() as session:
        await session.execute(
            text("""
                INSERT INTO task_schedules (task_id, user_id, trigger_time, action, advance_to, created_at)
                VALUES (:tid, :uid, :tt, :action, :advance_to, NOW())
            """),
            {"tid": task_id, "uid": user_id, "tt": trigger_time, "action": action, "advance_to": advance_to},
        )
        row = (await session.execute(text("SELECT LAST_INSERT_ID() AS schedule_id"))).mappings().one()
        await session.commit()
    return {"schedule_id": row["schedule_id"]}


async def delete_schedule(user_id: int, task_id: int) -> bool:
    """删除某任务的定时任务。"""
    affected = await _execute_write(
        "DELETE FROM task_schedules WHERE task_id = :tid AND user_id = :uid",
        {"tid": task_id, "uid": user_id},
    )
    return affected > 0


async def list_pending_schedules() -> list[dict]:
    """未触发的定时任务（JOIN 任务标题），供调度器启动时加载。"""
    return await _execute_read(
        """
        SELECT ts.schedule_id, ts.task_id, ts.user_id, ts.trigger_time, ts.action, ts.advance_to,
               ts.fired, ut.title
        FROM task_schedules ts
        JOIN user_tasks ut ON ut.task_id = ts.task_id
        WHERE ts.fired = 0 AND ts.trigger_time > NOW()
        """
    )


async def mark_schedule_fired(schedule_id: int) -> None:
    """标记定时任务已触发。"""
    await _execute_write(
        "UPDATE task_schedules SET fired = 1 WHERE schedule_id = :sid",
        {"sid": schedule_id},
    )


async def advance_task(task_id: int, status: str) -> None:
    """自动推进任务状态；done 时写 completed_at。"""
    if status == "done":
        await _execute_write(
            "UPDATE user_tasks SET status = 'done', completed_at = NOW() WHERE task_id = :tid",
            {"tid": task_id},
        )
    else:
        await _execute_write(
            "UPDATE user_tasks SET status = :status, completed_at = NULL WHERE task_id = :tid",
            {"tid": task_id, "status": status},
        )


# ─────────────── 请假 ───────────────

async def create_leave(user_id: int, day, note=None) -> dict:
    """创建请假记录，返回含 leave_id 的 dict。"""
    factory = _get_factory()
    async with factory() as session:
        await session.execute(
            text("""
                INSERT INTO leaves (user_id, day, note, created_at)
                VALUES (:uid, :day, :note, NOW())
            """),
            {"uid": user_id, "day": day, "note": note},
        )
        row = (await session.execute(text("SELECT LAST_INSERT_ID() AS leave_id"))).mappings().one()
        await session.commit()
    return {"leave_id": row["leave_id"]}


async def delete_leave(user_id: int, leave_id: int) -> bool:
    """删除请假记录。"""
    affected = await _execute_write(
        "DELETE FROM leaves WHERE leave_id = :lid AND user_id = :uid",
        {"lid": leave_id, "uid": user_id},
    )
    return affected > 0


async def list_leaves(user_id: int) -> list[dict]:
    """某用户请假列表，按日期升序。"""
    return await _execute_read(
        "SELECT leave_id, day, note FROM leaves WHERE user_id = :uid ORDER BY day ASC",
        {"uid": user_id},
    )


# ─────────────── 工作日集合 ───────────────

async def get_workday_sets(user_id: int, year: int) -> tuple[set, set, set]:
    """返回 (holidays, workdays, leaves) 三个 date 集合，供切分算法使用。"""
    h_rows = await _execute_read(
        "SELECT day, type FROM holidays WHERE YEAR(day) = :year", {"year": year}
    )
    holidays = {r["day"] for r in h_rows if r["type"] == "holiday"}
    workdays = {r["day"] for r in h_rows if r["type"] == "workday"}
    l_rows = await _execute_read(
        "SELECT day FROM leaves WHERE user_id = :uid AND YEAR(day) = :year",
        {"uid": user_id, "year": year},
    )
    leaves = {r["day"] for r in l_rows}
    return holidays, workdays, leaves


# ─────────────── 工作记录（日历聚合） ───────────────

async def get_worklog(user_id: int, year: int, month: int) -> dict:
    """某月工作记录聚合：按天完成数/创建数 + 总计 + 活跃天数 + 完成率。"""
    prefix = f"{year:04d}-{month:02d}"
    last_day = calendar.monthrange(year, month)[1]
    start = f"{prefix}-01 00:00:00"
    end = f"{prefix}-{last_day:02d} 23:59:59"
    rows = await _execute_read(
        """
        SELECT
            SUM(CASE WHEN completed_at IS NOT NULL THEN 1 ELSE 0 END) AS total_done,
            SUM(CASE WHEN created_at IS NOT NULL THEN 1 ELSE 0 END) AS total_created
        FROM user_tasks
        WHERE user_id = :uid
          AND (created_at >= :start OR completed_at >= :start)
          AND (created_at < :end OR completed_at < :end)
        """,
        {"uid": user_id, "start": start, "end": end},
    )
    total_done = int(rows[0]["total_done"] or 0)
    total_created = int(rows[0]["total_created"] or 0)

    done_rows = await _execute_read(
        """
        SELECT DATE(completed_at) AS d, COUNT(*) AS c
        FROM user_tasks
        WHERE user_id = :uid AND completed_at >= :start AND completed_at < :end
        GROUP BY DATE(completed_at)
        """,
        {"uid": user_id, "start": start, "end": end},
    )
    created_rows = await _execute_read(
        """
        SELECT DATE(created_at) AS d, COUNT(*) AS c
        FROM user_tasks
        WHERE user_id = :uid AND created_at >= :start AND created_at < :end
        GROUP BY DATE(created_at)
        """,
        {"uid": user_id, "start": start, "end": end},
    )
    done_by_day = {str(r["d"]): int(r["c"]) for r in done_rows}
    created_by_day = {str(r["d"]): int(r["c"]) for r in created_rows}
    active_days = len(set(done_by_day) | set(created_by_day))

    return {
        "done_by_day": done_by_day,
        "created_by_day": created_by_day,
        "total_done": total_done,
        "total_created": total_created,
        "active_days": active_days,
        "rate": round(total_done / total_created, 4) if total_created else 0.0,
    }


async def get_worklog_day(user_id: int, day: str) -> dict:
    """某日明细：当天完成的任务列表 + 创建的任务列表。"""
    done = await _execute_read(
        """
        SELECT task_id, title, completed_at
        FROM user_tasks
        WHERE user_id = :uid AND DATE(completed_at) = :day
        ORDER BY completed_at ASC
        """,
        {"uid": user_id, "day": day},
    )
    created = await _execute_read(
        """
        SELECT task_id, title, created_at
        FROM user_tasks
        WHERE user_id = :uid AND DATE(created_at) = :day
        ORDER BY created_at ASC
        """,
        {"uid": user_id, "day": day},
    )
    return {"done_tasks": done, "created_tasks": created}
