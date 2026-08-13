"""任务管理器 service — 任务 CRUD / 定时任务 / 请假 / 工作记录聚合

遵循 session_service 模式：模块级 _execute_read/_execute_write，原生 SQL。
"""
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
