# 任务管理器 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 Agent-Zs 增加任务管理器：左侧面板上下结构（会话 + 任务）、任务 CRUD 与 4 过滤、定时任务（提醒 + 自动推进）、大任务切分（今日/本月/本年）、日历视图工作记录。

**Architecture:** 最小侵入，复用现有 SSE + LangGraph + 单文件前端。新建 `app/tasks/` 模块（schemas / planner 纯函数 / service 原生 SQL / scheduler APScheduler），新增 `app/routers/tasks.py` 路由，在 LangGraph 增加 `task_plan` 意图与节点，扩展 `frontend.py` 左侧面板。切分逻辑确定性代码实现，LLM 只做意图分类。

**Tech Stack:** FastAPI + SQLAlchemy 2.0 异步（原生 `text()` SQL）、LangGraph、APScheduler 3.10、MySQL、单文件 HTML/CSS/JS 前端。

## Global Constraints

- 所有输出/注释/日志中文；变量名、函数名、类名用英文。
- 行级数据隔离：所有查询按 `user_id` 过滤（`user_id` 为 `int`，来自 JWT payload）。
- 状态枚举：`pending`(待办) / `doing`(处理中) / `done`(已完成)；「逾期」是派生标记（`deadline < now 且 status != done`），不落库。
- 定时任务 action：`remind`(仅提醒) / `remind_advance`(提醒 + 自动推进到 `advance_to`)。
- 节假日 `type`：`holiday`(法定节假日) / `workday`(调休上班)；请假单独存 `leaves` 表。
- service 层遵循 `session_service.py` 模式：模块级 `_execute_read`/`_execute_write`，函数签名传业务参数（不传 session）。
- 测试连真实库（conftest `DB_NAME=wms` 172.177.3.43:3309），service 集成测试用专用 `user_id=900001` 并在测试后清理。
- 切分算法确定性：LLM 只做意图分类与目标抽取，切分用纯 Python 函数。

---

### Task 1: 数据库表（4 张建表脚本）

**Files:**
- Create: `scripts/init_task_manager.sql`

**Interfaces:**
- Produces: 4 张表 `user_tasks` / `task_schedules` / `holidays` / `leaves`（字段名见下方 SQL，后续 Task 的 service SQL 严格引用这些字段）。

- [ ] **Step 1: 写建表脚本**

```sql
-- ============================================================
-- 任务管理器 4 张表
-- ============================================================

-- 1. 用户任务主表
CREATE TABLE IF NOT EXISTS user_tasks (
    task_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY COMMENT '任务ID',
    user_id BIGINT UNSIGNED NOT NULL COMMENT '用户ID',
    title VARCHAR(200) NOT NULL COMMENT '任务标题',
    status VARCHAR(20) DEFAULT 'pending' COMMENT 'pending/doing/done',
    priority TINYINT DEFAULT 0 COMMENT '优先级',
    deadline DATETIME NULL COMMENT '截止时间',
    parent_id BIGINT UNSIGNED NULL COMMENT '父任务ID',
    plan_detail JSON NULL COMMENT '规划细节',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    completed_at DATETIME NULL COMMENT '完成时间',
    INDEX idx_user (user_id),
    INDEX idx_status (status),
    INDEX idx_deadline (deadline),
    INDEX idx_parent (parent_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='用户任务表';

-- 2. 定时任务表
CREATE TABLE IF NOT EXISTS task_schedules (
    schedule_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY COMMENT '定时任务ID',
    task_id BIGINT UNSIGNED NOT NULL COMMENT '关联任务',
    user_id BIGINT UNSIGNED NOT NULL COMMENT '用户ID',
    trigger_time DATETIME NOT NULL COMMENT '触发时间',
    action VARCHAR(20) NOT NULL COMMENT 'remind/remind_advance',
    advance_to VARCHAR(20) NULL COMMENT 'doing/done',
    fired TINYINT DEFAULT 0 COMMENT '是否已触发',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    INDEX idx_task (task_id),
    INDEX idx_user (user_id),
    INDEX idx_trigger (trigger_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='定时任务表';

-- 3. 公共节假日表（内置只读）
CREATE TABLE IF NOT EXISTS holidays (
    holiday_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY COMMENT 'ID',
    day DATE NOT NULL COMMENT '日期',
    type VARCHAR(20) NOT NULL COMMENT 'holiday/workday',
    note VARCHAR(100) NULL COMMENT '备注',
    UNIQUE KEY uk_day (day)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='公共节假日表';

-- 4. 个人请假表
CREATE TABLE IF NOT EXISTS leaves (
    leave_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY COMMENT 'ID',
    user_id BIGINT UNSIGNED NOT NULL COMMENT '用户ID',
    day DATE NOT NULL COMMENT '请假日期',
    note VARCHAR(100) NULL COMMENT '备注',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    INDEX idx_user_day (user_id, day)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='个人请假表';

-- 预置 2026 年国庆/中秋调休示例（holiday=放假，workday=调休上班）
INSERT INTO holidays (day, type, note) VALUES
    ('2026-10-01', 'holiday', '国庆节'),
    ('2026-10-02', 'holiday', '国庆节'),
    ('2026-10-06', 'holiday', '中秋节')
ON DUPLICATE KEY UPDATE note = VALUES(note);
```

- [ ] **Step 2: 在测试库执行建表（幂等）**

Run: `mysql -h 172.177.3.43 -P 3309 -u wms -p'Zsds2604!' wms < scripts/init_task_manager.sql`
Expected: 无报错，Query OK。

- [ ] **Step 3: 验证 4 张表存在**

Run: `mysql -h 172.177.3.43 -P 3309 -u wms -p'Zsds2604!' wms -e "SHOW TABLES LIKE 'user_tasks'; SHOW TABLES LIKE 'task_schedules'; SHOW TABLES LIKE 'holidays'; SHOW TABLES LIKE 'leaves';"`
Expected: 4 行，每行一个表名。

- [ ] **Step 4: Commit**

```bash
git add scripts/init_task_manager.sql
git commit -m "feat: 任务管理器 4 张表建表脚本"
```

---

### Task 2: 工作日计算 + 大任务切分算法（纯函数）

**Files:**
- Create: `app/tasks/__init__.py`（空文件）
- Create: `app/tasks/planner.py`
- Test: `tests/test_task_planner.py`

**Interfaces:**
- Produces（后续 Task 5/6 依赖）:
  - `parse_plan_input(user_input: str) -> tuple[str, str]` — 返回 `(granularity, goal)`，granularity ∈ `{"today","month","year"}`
  - `is_workday(day: date, holidays: set[date], workdays: set[date], leaves: set[date]) -> bool`
  - `split_today(goal: str, today: date, off_time: str = "18:00") -> list[dict]`
  - `split_month(goal: str, year: int, month: int, holidays: set[date], workdays: set[date], leaves: set[date]) -> list[dict]`
  - `split_year(goal: str, year: int, holidays: set[date], workdays: set[date], leaves: set[date]) -> list[dict]`
  - 子任务 dict 结构统一为 `{"title": str, "date": "YYYY-MM-DD", "time": str | None}`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_task_planner.py
"""大任务切分算法测试（纯函数，零外部依赖）"""
from datetime import date
from app.tasks.planner import (
    parse_plan_input, is_workday, split_today, split_month, split_year,
)


class TestParsePlanInput:
    def test_today(self):
        assert parse_plan_input("今日任务：完成库存盘点") == ("today", "完成库存盘点")

    def test_month(self):
        assert parse_plan_input("本月任务：梳理采购流程") == ("month", "梳理采购流程")

    def test_year(self):
        assert parse_plan_input("本年任务：上线新系统") == ("year", "上线新系统")

    def test_no_goal_uses_default(self):
        assert parse_plan_input("今日任务") == ("today", "")


class TestIsWorkday:
    def test_weekday_is_workday(self):
        # 2026-08-13 是周四
        assert is_workday(date(2026, 8, 13), set(), set(), set()) is True

    def test_weekend_is_not_workday(self):
        # 2026-08-15 是周六
        assert is_workday(date(2026, 8, 15), set(), set(), set()) is False

    def test_holiday_not_workday(self):
        assert is_workday(date(2026, 10, 1), {date(2026, 10, 1)}, set(), set()) is False

    def test_makeup_workday_overrides_weekend(self):
        # 2026-08-16 周日，若标记为调休上班
        assert is_workday(date(2026, 8, 16), set(), {date(2026, 8, 16)}, set()) is True

    def test_leave_overrides_all(self):
        # 请假优先级最高，即使不是节假日
        assert is_workday(date(2026, 8, 13), set(), set(), {date(2026, 8, 13)}) is False


class TestSplitToday:
    def test_single_task_to_off_time(self):
        result = split_today("完成盘点", date(2026, 8, 13))
        assert result == [{"title": "完成盘点", "date": "2026-08-13", "time": "18:00"}]


class TestSplitMonth:
    def test_only_workdays(self):
        # 2026-08 有 21 个工作日（8/1 8/2 是周末）
        result = split_month("梳理流程", 2026, 8, set(), set(), set())
        dates = [r["date"] for r in result]
        assert all(d[8:10] not in ("01", "02", "08", "09", "15", "16", "22", "23", "29", "30") for d in dates)
        assert len(result) == 21

    def test_skip_holiday_and_leave(self):
        holidays = {date(2026, 8, 13)}
        leaves = {date(2026, 8, 14)}
        result = split_month("梳理流程", 2026, 8, holidays, set(), leaves)
        dates = [r["date"] for r in result]
        assert "2026-08-13" not in dates
        assert "2026-08-14" not in dates


class TestSplitYear:
    def test_12_month_milestones(self):
        result = split_year("上线系统", 2026, set(), set(), set())
        # 每个子任务标题含月份里程碑
        assert len(result) > 200  # 全年约 250 个工作日
        assert result[0]["title"].startswith("上线系统")
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_task_planner.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'app.tasks.planner'`

- [ ] **Step 3: 实现 `app/tasks/planner.py`**

```python
"""任务切分算法（确定性纯函数，零 LLM）

设计文档 §7：LLM 只做意图分类与目标抽取，切分由代码确定性完成。
"""
import calendar
from datetime import date

# 粒度关键词（长词在前，避免"今日"被"今年"误匹配）
_GRANULARITY_KEYWORDS = [
    ("today", ["今日任务", "今天任务", "今日计划", "今天计划", "今日", "今天"]),
    ("month", ["本月任务", "这个月任务", "本月计划", "这个月", "本月"]),
    ("year", ["本年任务", "今年任务", "年度任务", "本年计划", "今年计划", "年度计划", "本年", "今年"]),
]


def parse_plan_input(user_input: str) -> tuple[str, str]:
    """解析「今日/本月/本年任务」指令，返回 (granularity, goal)。

    granularity ∈ {"today","month","year"}；goal 为去掉粒度词与冒号后的目标文本。
    """
    text = user_input.strip()
    for granularity, keywords in _GRANULARITY_KEYWORDS:
        for kw in keywords:
            if kw in text:
                goal = text.replace(kw, "")
                goal = goal.lstrip("：:：,，。. ")
                return granularity, goal
    # 未命中粒度词时，默认按"今日任务"处理整句为目标
    return "today", text


def is_workday(day: date, holidays: set[date], workdays: set[date], leaves: set[date]) -> bool:
    """判断某天是否为工作日。

    优先级：个人请假 > 调休上班 > 法定节假日 > 默认（周一~周五工作）。
    """
    if day in leaves:
        return False
    if day in workdays:
        return True
    if day in holidays:
        return False
    return day.weekday() < 5


def split_today(goal: str, today: date, off_time: str = "18:00") -> list[dict]:
    """今日任务：整目标切到当天，1 天任务规划到下班时间。"""
    return [{"title": goal, "date": today.isoformat(), "time": off_time}]


def _workdays_in_month(year: int, month: int, holidays: set[date], workdays: set[date], leaves: set[date]) -> list[date]:
    """返回某月所有工作日的 date 列表。"""
    days = []
    num_days = calendar.monthrange(year, month)[1]
    for d in range(1, num_days + 1):
        day = date(year, month, d)
        if is_workday(day, holidays, workdays, leaves):
            days.append(day)
    return days


def split_month(goal: str, year: int, month: int, holidays: set[date], workdays: set[date], leaves: set[date]) -> list[dict]:
    """本月任务：按工作日均分到天，跳过节假日/请假。

    每个工作日生成一个阶段子任务，标题 = "{goal} - 阶段{i}"。
    """
    days = _workdays_in_month(year, month, holidays, workdays, leaves)
    return [
        {"title": f"{goal} - 阶段{i + 1}", "date": day.isoformat(), "time": None}
        for i, day in enumerate(days)
    ]


def split_year(goal: str, year: int, holidays: set[date], workdays: set[date], leaves: set[date]) -> list[dict]:
    """本年任务：先切到月里程碑，每月再按工作日展开到天。"""
    result = []
    for month in range(1, 13):
        days = _workdays_in_month(year, month, holidays, workdays, leaves)
        for i, day in enumerate(days):
            result.append({
                "title": f"{goal} - {month}月 阶段{i + 1}",
                "date": day.isoformat(),
                "time": None,
            })
    return result
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_task_planner.py -v`
Expected: 全部 PASS。

- [ ] **Step 5: Commit**

```bash
git add app/tasks/__init__.py app/tasks/planner.py tests/test_task_planner.py
git commit -m "feat: 大任务切分算法（今日/本月/本年，确定性纯函数）"
```

---

### Task 3: 任务 CRUD service（原生 SQL）

**Files:**
- Create: `app/tasks/schemas.py`
- Create: `app/tasks/service.py`
- Test: `tests/test_task_service.py`

**Interfaces:**
- Consumes: Task 1 的 `user_tasks` 表字段。
- Produces（Task 4/5/6/7 依赖）:
  - `create_task(user_id: int, title: str, deadline=None, priority: int = 0, parent_id=None) -> dict` — 返回含 `task_id` 的 dict
  - `list_tasks(user_id: int, filter: str = "all", q: str = "") -> list[dict]` — 每项含 `task_id/title/status/priority/deadline/created_at/completed_at/overdue`
  - `update_task(user_id: int, task_id: int, **fields) -> dict | None` — 支持 `title/status/deadline/priority`；`status="done"` 时写 `completed_at=NOW()`，否则置 NULL
  - `delete_task(user_id: int, task_id: int) -> bool`
  - `get_task(user_id: int, task_id: int) -> dict | None`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_task_service.py
"""任务 CRUD service 集成测试（连真实库，专用 user_id 隔离 + 清理）"""
import pytest
from datetime import datetime, timedelta
from app.tasks.service import (
    create_task, list_tasks, update_task, delete_task, get_task,
)

TEST_USER = 900001


@pytest.fixture(autouse=True)
async def cleanup():
    """测试前清理残留，测试后清理数据"""
    from app.tasks.service import _execute_write
    yield
    await _execute_write("DELETE FROM user_tasks WHERE user_id = :uid", {"uid": TEST_USER})


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
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_task_service.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'app.tasks.service'`

- [ ] **Step 3: 实现 `app/tasks/schemas.py`**

```python
"""任务管理器 Pydantic 模型"""
from datetime import datetime, date
from pydantic import BaseModel


class TaskCreate(BaseModel):
    title: str
    deadline: datetime | None = None
    priority: int = 0


class TaskUpdate(BaseModel):
    title: str | None = None
    status: str | None = None  # pending/doing/done
    deadline: datetime | None = None
    priority: int | None = None


class ScheduleCreate(BaseModel):
    trigger_time: datetime
    action: str  # remind / remind_advance
    advance_to: str | None = None  # doing / done


class LeaveCreate(BaseModel):
    day: date
    note: str | None = None
```

- [ ] **Step 4: 实现 `app/tasks/service.py`（任务 CRUD 部分）**

```python
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
    result = await _execute_read(
        """
        INSERT INTO user_tasks (user_id, title, status, priority, deadline, parent_id, created_at)
        VALUES (:uid, :title, 'pending', :priority, :deadline, :parent_id, NOW())
        """,
        {"uid": user_id, "title": title, "priority": priority, "deadline": deadline, "parent_id": parent_id},
    )
    # 取回自增主键
    rows = await _execute_read("SELECT LAST_INSERT_ID() AS task_id")
    return {"task_id": rows[0]["task_id"]}


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
```

- [ ] **Step 5: 运行测试确认通过**

Run: `python -m pytest tests/test_task_service.py -v`
Expected: 全部 PASS。

- [ ] **Step 6: Commit**

```bash
git add app/tasks/schemas.py app/tasks/service.py tests/test_task_service.py
git commit -m "feat: 任务 CRUD service（原生 SQL，行级隔离）"
```

---

### Task 4: 定时任务 + 请假 + 工作记录聚合 service

**Files:**
- Modify: `app/tasks/service.py`（追加函数）
- Test: `tests/test_task_schedule_service.py`

**Interfaces:**
- Consumes: Task 1 的 `task_schedules` / `leaves` / `user_tasks` 表；Task 3 的 `_execute_read`/`_execute_write`。
- Produces（Task 5/6/7 依赖）:
  - `create_schedule(user_id: int, task_id: int, trigger_time, action: str, advance_to=None) -> dict`
  - `delete_schedule(user_id: int, task_id: int) -> bool`
  - `list_pending_schedules() -> list[dict]` — 未触发的所有记录，JOIN `user_tasks.title`
  - `mark_schedule_fired(schedule_id: int) -> None`
  - `advance_task(task_id: int, status: str) -> None` — 自动推进（done 时写 completed_at）
  - `create_leave(user_id: int, day, note=None) -> dict`
  - `delete_leave(user_id: int, leave_id: int) -> bool`
  - `list_leaves(user_id: int) -> list[dict]`
  - `get_workday_sets(user_id: int, year: int) -> tuple[set, set, set]` — 返回 `(holidays, workdays, leaves)`，date 集合
  - `get_worklog(user_id: int, year: int, month: int) -> dict` — 返回 `{done_by_day, created_by_day, total_done, total_created, active_days, rate}`
  - `get_worklog_day(user_id: int, day: str) -> dict` — 返回 `{done_tasks: [...], created_tasks: [...]}`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_task_schedule_service.py
"""定时任务 + 请假 + 工作记录聚合集成测试"""
import pytest
from datetime import datetime, date
from app.tasks.service import (
    create_task, create_schedule, delete_schedule, list_pending_schedules,
    mark_schedule_fired, advance_task, get_task,
    create_leave, list_leaves, delete_leave, get_worklog, get_workday_sets,
)

TEST_USER = 900001


@pytest.fixture(autouse=True)
async def cleanup():
    from app.tasks.service import _execute_write
    yield
    await _execute_write("DELETE FROM user_tasks WHERE user_id = :uid", {"uid": TEST_USER})
    await _execute_write("DELETE FROM task_schedules WHERE user_id = :uid", {"uid": TEST_USER})
    await _execute_write("DELETE FROM leaves WHERE user_id = :uid", {"uid": TEST_USER})


@pytest.mark.asyncio
async def test_create_schedule():
    task = await create_task(TEST_USER, "带提醒任务")
    sched = await create_schedule(TEST_USER, task["task_id"], datetime(2026, 8, 20, 9, 0), "remind")
    assert sched["schedule_id"] > 0
    pending = await list_pending_schedules()
    assert any(s["task_id"] == task["task_id"] and s["fired"] == 0 for s in pending)


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
    await create_leave(TEST_USER, date(2026, 8, 14), "年假")
    leaves = await list_leaves(TEST_USER)
    assert any(l["day"] == date(2026, 8, 14) for l in leaves)


@pytest.mark.asyncio
async def test_worklog_aggregation():
    t1 = await create_task(TEST_USER, "已完成任务")
    await advance_task(t1["task_id"], "done")
    await create_task(TEST_USER, "待办任务")
    log = await get_worklog(TEST_USER, 2026, 8)
    assert log["total_done"] >= 1
    assert log["total_created"] >= 2
    assert 0 <= log["rate"] <= 1
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_task_schedule_service.py -v`
Expected: FAIL，`ImportError: cannot import name 'create_schedule'`

- [ ] **Step 3: 实现（追加到 `app/tasks/service.py` 末尾）**

```python
# ─────────────── 定时任务 ───────────────

async def create_schedule(user_id: int, task_id: int, trigger_time, action: str, advance_to=None) -> dict:
    """创建定时任务，返回含 schedule_id 的 dict。"""
    await _execute_write(
        """
        INSERT INTO task_schedules (task_id, user_id, trigger_time, action, advance_to, created_at)
        VALUES (:tid, :uid, :tt, :action, :advance_to, NOW())
        """,
        {"tid": task_id, "uid": user_id, "tt": trigger_time, "action": action, "advance_to": advance_to},
    )
    rows = await _execute_read("SELECT LAST_INSERT_ID() AS schedule_id")
    return {"schedule_id": rows[0]["schedule_id"]}


async def delete_schedule(user_id: int, task_id: int) -> bool:
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
               ut.title
        FROM task_schedules ts
        JOIN user_tasks ut ON ut.task_id = ts.task_id
        WHERE ts.fired = 0 AND ts.trigger_time > NOW()
        """
    )


async def mark_schedule_fired(schedule_id: int) -> None:
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
    await _execute_write(
        "INSERT INTO leaves (user_id, day, note, created_at) VALUES (:uid, :day, :note, NOW())",
        {"uid": user_id, "day": day, "note": note},
    )
    rows = await _execute_read("SELECT LAST_INSERT_ID() AS leave_id")
    return {"leave_id": rows[0]["leave_id"]}


async def delete_leave(user_id: int, leave_id: int) -> bool:
    affected = await _execute_write(
        "DELETE FROM leaves WHERE leave_id = :lid AND user_id = :uid",
        {"lid": leave_id, "uid": user_id},
    )
    return affected > 0


async def list_leaves(user_id: int) -> list[dict]:
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
        {"uid": user_id, "start": prefix + "-01 00:00:00", "end": f"{prefix}-31 23:59:59"},
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
        {"uid": user_id, "start": prefix + "-01 00:00:00", "end": f"{prefix}-31 23:59:59"},
    )
    created_rows = await _execute_read(
        """
        SELECT DATE(created_at) AS d, COUNT(*) AS c
        FROM user_tasks
        WHERE user_id = :uid AND created_at >= :start AND created_at < :end
        GROUP BY DATE(created_at)
        """,
        {"uid": user_id, "start": prefix + "-01 00:00:00", "end": f"{prefix}-31 23:59:59"},
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
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_task_schedule_service.py -v`
Expected: 全部 PASS。

- [ ] **Step 5: Commit**

```bash
git add app/tasks/service.py tests/test_task_schedule_service.py
git commit -m "feat: 定时任务 + 请假 + 工作记录聚合 service"
```

---

### Task 5: REST API 路由

**Files:**
- Create: `app/routers/tasks.py`
- Modify: `app/main.py:14,100-110`（导入 + 注册路由）
- Test: `tests/test_tasks_api.py`

**Interfaces:**
- Consumes: Task 3/4 的 service 函数、`verify_token`。
- Produces: 8 个端点（前缀 `/api/v1/tasks`）：
  - `GET /tasks`、`POST /tasks`、`PATCH /tasks/{id}`、`DELETE /tasks/{id}`
  - `POST /tasks/{id}/schedule`、`DELETE /tasks/{id}/schedule`
  - `GET /tasks/worklog`、`GET /tasks/worklog/day`
  - 响应统一 `{"status": "ok", ...}`，错误用 `HTTPException`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_tasks_api.py
"""任务 API 集成测试（TestClient + 真实 JWT）"""
from datetime import datetime
from tests.conftest import client, auth_headers  # noqa: F401 复用 fixture


def test_create_and_list_task(client, auth_headers):
    r = client.post("/api/v1/tasks", json={"title": "API测试任务"}, headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    task_id = r.json()["task_id"]

    r2 = client.get("/api/v1/tasks", headers=auth_headers)
    assert r2.status_code == 200
    assert any(t["task_id"] == task_id for t in r2.json()["tasks"])


def test_update_and_delete_task(client, auth_headers):
    r = client.post("/api/v1/tasks", json={"title": "待完成"}, headers=auth_headers)
    task_id = r.json()["task_id"]

    r2 = client.patch(f"/api/v1/tasks/{task_id}", json={"status": "done"}, headers=auth_headers)
    assert r2.json()["task"]["status"] == "done"

    r3 = client.delete(f"/api/v1/tasks/{task_id}", headers=auth_headers)
    assert r3.json()["status"] == "ok"


def test_worklog_endpoint(client, auth_headers):
    r = client.get("/api/v1/tasks/worklog?year=2026&month=8", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert "total_done" in data and "rate" in data
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_tasks_api.py -v`
Expected: FAIL，404（路由未注册）。

- [ ] **Step 3: 实现 `app/routers/tasks.py`**

```python
"""任务管理器端点 — 任务 CRUD / 定时任务 / 请假 / 工作记录"""
import logging
from fastapi import APIRouter, Depends, HTTPException

from app.gateway.auth import verify_token
from app.tasks import service
from app.tasks.schemas import TaskCreate, TaskUpdate, ScheduleCreate, LeaveCreate

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/tasks")
async def list_tasks(filter: str = "all", q: str = "", user_info: dict = Depends(verify_token)):
    """任务列表（filter=all/done/pending/doing，q=关键词）"""
    tasks = await service.list_tasks(user_info["user_id"], filter, q)
    return {"status": "ok", "tasks": tasks}


@router.post("/tasks")
async def create_task(body: TaskCreate, user_info: dict = Depends(verify_token)):
    """创建任务"""
    task = await service.create_task(
        user_info["user_id"], body.title, body.deadline, body.priority
    )
    return {"status": "ok", **task}


@router.patch("/tasks/{task_id}")
async def update_task(task_id: int, body: TaskUpdate, user_info: dict = Depends(verify_token)):
    """更新任务（标题/状态/截止/优先级）"""
    fields = {k: v for k, v in body.model_dump().items() if v is not None}
    task = await service.update_task(user_info["user_id"], task_id, **fields)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在或无权操作")
    return {"status": "ok", "task": task}


@router.delete("/tasks/{task_id}")
async def delete_task(task_id: int, user_info: dict = Depends(verify_token)):
    """删除任务"""
    ok = await service.delete_task(user_info["user_id"], task_id)
    if not ok:
        raise HTTPException(status_code=404, detail="任务不存在或无权操作")
    return {"status": "ok", "message": "任务已删除"}


@router.post("/tasks/{task_id}/schedule")
async def create_schedule(task_id: int, body: ScheduleCreate, user_info: dict = Depends(verify_token)):
    """创建定时任务"""
    task = await service.get_task(user_info["user_id"], task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在或无权操作")
    sched = await service.create_schedule(
        user_info["user_id"], task_id, body.trigger_time, body.action, body.advance_to
    )
    # 注册到调度器
    from app.tasks.scheduler import task_scheduler
    await task_scheduler.add_schedule({
        "schedule_id": sched["schedule_id"], "task_id": task_id,
        "user_id": user_info["user_id"], "trigger_time": body.trigger_time,
        "action": body.action, "advance_to": body.advance_to, "title": task["title"],
    })
    return {"status": "ok", **sched}


@router.delete("/tasks/{task_id}/schedule")
async def remove_schedule(task_id: int, user_info: dict = Depends(verify_token)):
    """取消定时任务"""
    ok = await service.delete_schedule(user_info["user_id"], task_id)
    if not ok:
        raise HTTPException(status_code=404, detail="定时任务不存在")
    return {"status": "ok", "message": "定时任务已取消"}


@router.post("/tasks/leaves")
async def create_leave(body: LeaveCreate, user_info: dict = Depends(verify_token)):
    """添加请假"""
    leave = await service.create_leave(user_info["user_id"], body.day, body.note)
    return {"status": "ok", **leave}


@router.get("/tasks/leaves")
async def list_leaves(user_info: dict = Depends(verify_token)):
    """请假列表"""
    leaves = await service.list_leaves(user_info["user_id"])
    return {"status": "ok", "leaves": leaves}


@router.get("/tasks/worklog")
async def worklog(year: int, month: int, user_info: dict = Depends(verify_token)):
    """某月工作记录聚合（日历视图）"""
    log = await service.get_worklog(user_info["user_id"], year, month)
    return {"status": "ok", **log}


@router.get("/tasks/worklog/day")
async def worklog_day(date: str, user_info: dict = Depends(verify_token)):
    """某日工作记录明细"""
    detail = await service.get_worklog_day(user_info["user_id"], date)
    return {"status": "ok", **detail}
```

- [ ] **Step 4: 在 `app/main.py` 注册路由**

Modify `app/main.py`：
- 第 14 行 import 加 `tasks`：
  `from app.routers import health, query, report, write, rag, admin, workflow, frontend, admin_config, auth, sessions, tasks`
- 第 109 行后加：
  `app.include_router(tasks.router, prefix="/api/v1", tags=["任务"])`

- [ ] **Step 5: 运行测试确认通过**

Run: `python -m pytest tests/test_tasks_api.py -v`
Expected: 全部 PASS。

- [ ] **Step 6: Commit**

```bash
git add app/routers/tasks.py app/main.py tests/test_tasks_api.py
git commit -m "feat: 任务管理器 REST API 路由"
```

---

### Task 6: LangGraph task_plan 节点 + 意图分类

**Files:**
- Modify: `app/orchestrator/planner.py:23-80`（`INTENT_RULES` 加 `task_plan` 关键词、`VALID_INTENTS` 加 `task_plan`、`INTENT_CLASSIFY_PROMPT` 加类别）
- Modify: `app/orchestrator/langgraph_flow.py`（加 `task_plan_node` + `route_by_intent` 映射 + 图节点注册）
- Test: `tests/test_task_plan_node.py`

**Interfaces:**
- Consumes: Task 2 的 `parse_plan_input`/`split_*`，Task 4 的 `get_workday_sets`。
- Produces: `task_plan_node(state) -> dict` — 返回 `{"result": {"status":"ok", "data": [...子任务], "message": ..., "preview": True}, "agent_name": "task_planner"}`。切分结果**不落库**，message 提示「预览，确认后落库」。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_task_plan_node.py
"""task_plan 节点 + 意图分类测试（monkeypatch mock 基础设施）"""
import pytest
from app.orchestrator import langgraph_flow
from app.orchestrator.langgraph_flow import route_by_intent, task_plan_node


class FakeSessionMemory:
    async def add_message(self, *a, **k): pass
    async def get_messages(self, *a, **k): return []
    async def get_context(self, *a, **k): return {}
    async def update_context(self, *a, **k): pass


class FakeTaskMemory:
    async def save_task(self, *a, **k): return True


class FakeMemoryExtractor:
    async def should_extract(self, m): return False


class FakeAuditLogger:
    async def log(self, *a, **k): pass


@pytest.fixture(autouse=True)
def mock_infra(monkeypatch):
    monkeypatch.setattr(langgraph_flow, "session_memory", FakeSessionMemory())
    monkeypatch.setattr(langgraph_flow, "task_memory", FakeTaskMemory())
    monkeypatch.setattr(langgraph_flow, "memory_extractor", FakeMemoryExtractor())
    monkeypatch.setattr(langgraph_flow, "audit_logger", FakeAuditLogger())
    langgraph_flow._compiled_graph = None


def test_route_by_intent_task_plan():
    assert route_by_intent({"intent": "task_plan"}) == "task_plan_node"


@pytest.mark.asyncio
async def test_task_plan_node_today(monkeypatch):
    async def fake_workday_sets(user_id, year):
        return set(), set(), set()
    monkeypatch.setattr("app.orchestrator.langgraph_flow.get_workday_sets", fake_workday_sets)
    result = await task_plan_node({
        "user_input": "今日任务：完成库存盘点",
        "user_id": 1,
    })
    assert result["result"]["status"] == "ok"
    assert result["result"]["preview"] is True
    assert result["result"]["data"][0]["title"] == "完成库存盘点"
    assert result["agent_name"] == "task_planner"


@pytest.mark.asyncio
async def test_classify_intent_task_plan(monkeypatch):
    """规则引擎识别「本月任务」为 task_plan 意图"""
    from app.orchestrator.planner import planner
    assert await planner.classify_intent("本月任务：梳理采购流程") == "task_plan"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_task_plan_node.py -v`
Expected: FAIL，`test_route_by_intent_task_plan` 断言失败（当前映射到 data_node），`test_classify_intent_task_plan` 返回非 task_plan。

- [ ] **Step 3: 修改 `app/orchestrator/planner.py`**

在 `INTENT_RULES`（第 23 行列表）**开头**加入 task_plan（放最前，避免「今日」等词与 time 的「日历」「星期几」冲突时被抢）：

```python
INTENT_RULES = [
    # 任务规划（今日/本月/本年任务切分）——放最前，长词优先，避免误判
    ("task_plan", [
        "今日任务", "今天任务", "本月任务", "本年任务", "今年任务",
        "今日计划", "本月计划", "年度任务", "年度计划", "今天做什么",
        "任务切分", "拆分任务", "规划任务",
    ]),
    # 记忆/回顾
    ("memory", [ ... ]),  # 保持不变
    ...
]
```

`VALID_INTENTS`（第 80 行）改为：

```python
VALID_INTENTS = {"query", "create", "update", "report", "knowledge", "memory", "time", "weather", "chat", "task_plan"}
```

`INTENT_CLASSIFY_PROMPT`（第 83 行起）在 `【分类规则】` 的类别列表中加入：

```
- task_plan：
  用户希望规划/切分任务，输入包含「今日任务」「本月任务」「本年任务」等。
  示例：
  “今日任务：完成库存盘点”
  “本月任务：梳理采购流程”
```

并在第 162 行的输出格式行改为：
`query / create / update / report / knowledge / memory / time / weather / chat / task_plan`

- [ ] **Step 4: 修改 `app/orchestrator/langgraph_flow.py`**

在 import 区（第 30 行附近）加：

```python
from app.tasks.planner import parse_plan_input, split_today, split_month, split_year
from app.tasks.service import get_workday_sets
```

在 LLM 节点区（第 331 行 weather_node 之后）加 `task_plan_node`：

```python
async def task_plan_node(state: AgentState) -> dict:
    """任务规划节点（确定性切分，零 LLM）

    设计文档 §7：LLM 已在 classify_intent 判定 task_plan 意图，
    此处用纯函数按粒度切分，返回预览（不落库）。
    """
    user_input = state["user_input"]
    granularity, goal = parse_plan_input(user_input)
    goal = goal or "待规划任务"
    today = datetime.now().date()
    user_id = state.get("user_id", 0)

    if granularity == "today":
        items = split_today(goal, today)
    else:
        holidays, workdays, leaves = await get_workday_sets(user_id, today.year)
        if granularity == "month":
            items = split_month(goal, today.year, today.month, holidays, workdays, leaves)
        else:  # year
            items = split_year(goal, today.year, holidays, workdays, leaves)

    gran_cn = {"today": "今日", "month": "本月", "year": "本年"}[granularity]
    message = (
        f"【{gran_cn}任务规划预览】已将「{goal}」切分为 {len(items)} 个子任务，"
        f"确认后落库（目前为预览，未写入任务表）。"
    )
    return {
        "result": {
            "status": "ok",
            "data": items,
            "sql": None,
            "message": message,
            "preview": True,
        },
        "agent_name": "task_planner",
    }
```

`route_by_intent`（第 358 行）的 mapping 加：

```python
"task_plan": "task_plan_node",
```

`build_graph`（第 384 行起）：
- 加节点注册：`g.add_node("task_plan_node", _with_progress("正在规划任务...", task_plan_node))`
- `route_by_intent` 的 conditional_edges 字典加 `"task_plan_node": "task_plan_node"`
- 执行节点列表（第 427 行）加 `"task_plan_node"`

- [ ] **Step 5: 运行测试确认通过**

Run: `python -m pytest tests/test_task_plan_node.py tests/test_langgraph_flow.py -v`
Expected: 全部 PASS（含原有 langgraph 测试不回归）。

- [ ] **Step 6: Commit**

```bash
git add app/orchestrator/planner.py app/orchestrator/langgraph_flow.py tests/test_task_plan_node.py
git commit -m "feat: task_plan 节点 + 意图分类（大任务切分预览）"
```

---

### Task 7: APScheduler 调度器 + SSE 推送

**Files:**
- Create: `app/tasks/scheduler.py`
- Modify: `requirements.txt`（加 apscheduler）
- Modify: `app/main.py`（lifespan 启动/停止调度器 + 注册 SSE 端点路由）
- Create: `app/routers/tasks.py`（追加 SSE 端点，或新建 `app/routers/tasks_events.py`）
- Test: `tests/test_task_scheduler.py`

**Interfaces:**
- Consumes: Task 4 的 `list_pending_schedules`/`mark_schedule_fired`/`advance_task`；Task 5 的 `add_schedule` 调用。
- Produces: 全局单例 `task_scheduler`，方法 `start/stop/add_schedule/remove_schedule/subscribe/unsubscribe`。SSE 端点 `GET /api/v1/tasks/events`（`text/event-stream`，订阅当前用户的事件队列）。

- [ ] **Step 1: 加依赖**

Modify `requirements.txt`（第 31 行 redis 之后）加：

```
# 定时任务调度
APScheduler==3.10.4
```

Run: `pip install APScheduler==3.10.4`
Expected: 安装成功。

- [ ] **Step 2: 写失败测试**

```python
# tests/test_task_scheduler.py
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
```

- [ ] **Step 3: 运行测试确认失败**

Run: `python -m pytest tests/test_task_scheduler.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'app.tasks.scheduler'`

- [ ] **Step 4: 实现 `app/tasks/scheduler.py`**

```python
"""任务定时调度器（APScheduler AsyncIOScheduler）+ SSE 推送 pub/sub"""
import asyncio
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.tasks.service import list_pending_schedules, mark_schedule_fired, advance_task

logger = logging.getLogger(__name__)


class TaskScheduler:
    """定时任务调度 + 按 user_id 的 SSE 订阅推送"""

    def __init__(self):
        self._scheduler: AsyncIOScheduler | None = None
        self._subscribers: dict[int, set[asyncio.Queue]] = {}

    async def start(self):
        """启动调度器并加载未触发任务"""
        if self._scheduler is not None:
            return
        self._scheduler = AsyncIOScheduler()
        self._scheduler.start()
        for sched in await list_pending_schedules():
            self._add_job(sched)
        logger.info(f"任务调度器启动，加载 {len(self._subscribers) and ''} 个定时任务")

    async def stop(self):
        if self._scheduler is not None:
            self._scheduler.shutdown(wait=False)
            self._scheduler = None

    def _add_job(self, sched: dict):
        if self._scheduler is None:
            return
        self._scheduler.add_job(
            self._fire,
            "date",
            run_date=sched["trigger_time"],
            args=[sched],
            id=str(sched["schedule_id"]),
            replace_existing=True,
        )

    async def add_schedule(self, sched: dict):
        self._add_job(sched)

    async def remove_schedule(self, schedule_id: int):
        if self._scheduler is not None:
            try:
                self._scheduler.remove_job(str(schedule_id))
            except Exception:
                pass

    async def _fire(self, sched: dict):
        """触发定时任务：标记已触发 + 可选自动推进 + SSE 推送提醒"""
        try:
            await mark_schedule_fired(sched["schedule_id"])
            if sched.get("action") == "remind_advance" and sched.get("advance_to"):
                await advance_task(sched["task_id"], sched["advance_to"])
            await self._notify(sched["user_id"], {
                "type": "task_remind",
                "task_id": sched["task_id"],
                "message": f"⏰ 任务提醒：{sched.get('title', '')}",
            })
        except Exception as e:
            logger.error(f"定时任务触发失败: {e}", exc_info=True)

    async def subscribe(self, user_id: int) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._subscribers.setdefault(user_id, set()).add(q)
        return q

    def unsubscribe(self, user_id: int, q: asyncio.Queue):
        subs = self._subscribers.get(user_id)
        if subs:
            subs.discard(q)

    async def _notify(self, user_id: int, event: dict):
        for q in self._subscribers.get(user_id, set()):
            await q.put(event)


# 全局单例
task_scheduler = TaskScheduler()
```

- [ ] **Step 5: 运行测试确认通过**

Run: `python -m pytest tests/test_task_scheduler.py -v`
Expected: 全部 PASS。

- [ ] **Step 6: 接入 `app/main.py` lifespan**

在 `lifespan` 里 `task_worker.stop()` 之后、`close_db()` 之前加启动/停止：

```python
    # 启动任务调度器
    from app.tasks.scheduler import task_scheduler
    await task_scheduler.start()
    logger.info("任务调度器启动完成")
```

在 yield 之后（`task_worker.stop()` 前后均可）：

```python
    # 停止任务调度器
    from app.tasks.scheduler import task_scheduler
    await task_scheduler.stop()
```

- [ ] **Step 7: 追加 SSE 端点到 `app/routers/tasks.py`**

```python
from fastapi.responses import StreamingResponse
import asyncio
import json


@router.get("/tasks/events")
async def task_events(request, user_info: dict = Depends(verify_token)):
    """SSE 订阅：定时任务提醒实时推送（按 user_id 隔离）"""
    from app.tasks.scheduler import task_scheduler

    queue = await task_scheduler.subscribe(user_info["user_id"])

    async def gen():
        try:
            while True:
                event = await queue.get()
                if await request.is_disconnected():
                    break
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        finally:
            task_scheduler.unsubscribe(user_info["user_id"], queue)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )
```

- [ ] **Step 8: Commit**

```bash
git add app/tasks/scheduler.py app/main.py app/routers/tasks.py requirements.txt tests/test_task_scheduler.py
git commit -m "feat: APScheduler 定时调度 + SSE 提醒推送"
```

---

### Task 8: 前端改造（左侧面板 + 任务列表 + 日历视图）

**Files:**
- Modify: `app/routers/frontend.py`（`index()` 返回的 HTML/CSS/JS）

**Interfaces:**
- Consumes: Task 5/6/7 的 REST API 与 SSE 端点。
- Produces: 左侧面板上下结构（会话区 + 任务区）、任务 4 tab + 搜索、日历视图（月/年 + 点某天明细）、SSE 提醒角标。

> 设计稿 [task-manager-mockup.html](../../ui-mockup/task-manager-mockup.html) 已含完整前端实现（HTML/CSS/JS）。本 Task 将 mockup 的实现移植到 `frontend.py`，并把 mockup 里的 `SAMPLE_TASKS` 假数据替换为真实 API 调用。验证为手动浏览器检查（项目无前端测试框架）。

- [ ] **Step 1: 扩展 CSS**

在 `frontend.py` 的 `<style>` 内（第 42 行 `.no-sessions` 之后）追加任务区与日历样式（从 mockup 复制，保留 `--primary/#1890ff` 等变量）：

```css
/* ── 任务区 ── */
.task-panel { border-top: 1px solid #e8e8e8; max-height: 45%; display: flex; flex-direction: column; }
.task-panel .task-header { padding: 12px 16px; display: flex; justify-content: space-between; align-items: center; cursor: pointer; }
.task-tabs { display: flex; padding: 0 12px 8px; gap: 4px; }
.task-tab { flex: 1; padding: 6px 0; text-align: center; font-size: 12px; border: 1px solid #e8e8e8; border-radius: 6px; cursor: pointer; color: #666; }
.task-tab.active { border-color: #1890ff; color: #1890ff; background: #e6f7ff; }
.task-list { overflow-y: auto; padding: 0 8px 8px; flex: 1; }
.task-item { padding: 8px 10px; border-radius: 6px; cursor: pointer; display: flex; align-items: center; gap: 6px; }
.task-item:hover { background: #f5f5f5; }
.task-item .dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.task-item .dot.pending { background: #1890ff; }
.task-item .dot.doing { background: #fa8c16; }
.task-item .dot.done { background: #52c41a; }
.task-item .dot.overdue { background: #ff4d4f; }
/* ── 日历视图（从 mockup 移植 .cal-nav/.cal/.cal-cell/.cal-detail/.year-grid/.mini-cal/.cal-legend）── */
```

（完整日历 CSS 从 mockup 的 `.cal-nav` 至 `.cal-legend` 段落复制。）

- [ ] **Step 2: 扩展 HTML（侧边栏 + 主区日历入口）**

将侧边栏 `.sidebar`（第 106-114 行）改为上下结构，在 `#sessionList` 之后加任务面板：

```html
<div class="sidebar">
    <div class="sidebar-header">
        <h3>对话列表 <span id="sessionCount"></span></h3>
        <button class="new-chat-btn" onclick="newChat()">＋ 新对话</button>
    </div>
    <div class="session-list" id="sessionList">
        <div class="no-sessions">加载中...</div>
    </div>
    <div class="task-panel" id="taskPanel">
        <div class="task-header" onclick="toggleTaskPanel()">
            <span>任务列表 <span id="taskCount"></span></span><span id="taskArrow">▾</span>
        </div>
        <div class="task-tabs" id="taskTabs">
            <div class="task-tab active" data-filter="all" onclick="switchTaskTab('all')">全部</div>
            <div class="task-tab" data-filter="done" onclick="switchTaskTab('done')">已完成</div>
            <div class="task-tab" data-filter="pending" onclick="switchTaskTab('pending')">待办</div>
            <div class="task-tab" data-filter="doing" onclick="switchTaskTab('doing')">处理中</div>
        </div>
        <input type="text" id="taskSearch" placeholder="搜索任务..." oninput="loadTasks()" style="margin:0 12px 6px;padding:6px 10px;border:1px solid #e8e8e8;border-radius:6px;font-size:12px;">
        <div class="task-list" id="taskList"></div>
    </div>
</div>
```

主区域 topbar（第 118-121 行）加「工作记录」切换按钮：

```html
<div class="topbar">
    <h1>AI 智能助手</h1>
    <span class="user-info">
        <a onclick="switchMainView('chat')">聊天</a> |
        <a onclick="switchMainView('calendar')">工作记录</a> |
        <span id="userNameDisplay"></span> | <a onclick="logout()">退出</a>
    </span>
</div>
```

在 `.chat-area` 之后加日历容器（从 mockup 复制 `#calMonth` + `#calYear` + 顶部 4 卡片结构）。

- [ ] **Step 3: 扩展 JS（任务 CRUD + 日历 + SSE）**

在 `<script>` 内追加：

```javascript
const API_TASKS = '/api/v1/tasks';
let taskFilter = 'all';
let calYear = new Date().getFullYear(), calMonth = new Date().getMonth();

async function loadTasks() {
    const q = document.getElementById('taskSearch').value.trim();
    const res = await fetch(`${API_TASKS}?filter=${taskFilter}&q=${encodeURIComponent(q)}`, {
        headers: { 'Authorization': `Bearer ${token}` }
    });
    const data = await res.json();
    renderTaskList(data.tasks || []);
}
function renderTaskList(tasks) {
    const el = document.getElementById('taskList');
    document.getElementById('taskCount').textContent = tasks.length ? `(${tasks.length})` : '';
    el.innerHTML = tasks.length ? tasks.map(t => `
        <div class="task-item" onclick="taskMenu(${t.task_id})">
            <span class="dot ${t.overdue ? 'overdue' : t.status}"></span>
            <span style="flex:1;font-size:12px;color:#333;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${escapeHtml(t.title)}</span>
        </div>`).join('') : '<div style="padding:20px;text-align:center;color:#bbb;font-size:12px;">暂无任务</div>';
}
function switchTaskTab(filter) {
    taskFilter = filter;
    document.querySelectorAll('.task-tab').forEach(t => t.classList.toggle('active', t.dataset.filter === filter));
    loadTasks();
}
function toggleTaskPanel() {
    const list = document.getElementById('taskList');
    const hidden = list.style.display === 'none';
    list.style.display = hidden ? '' : 'none';
    document.getElementById('taskArrow').textContent = hidden ? '▾' : '▸';
}

// 日历视图（从 mockup 移植 renderMonth/showDay/renderDetail/calShift/switchCalView/renderYear，
// 但把 dayStats() 假数据换成 GET /api/v1/tasks/worklog?year=&month= 的真实聚合）
async function renderMonth() {
    const res = await fetch(`${API_TASKS}/worklog?year=${calYear}&month=${calMonth + 1}`, {
        headers: { 'Authorization': `Bearer ${token}` }
    });
    const d = await res.json();
    // 用 d.done_by_day / d.created_by_day 填充月历格子 + 更新 4 张数字卡片
}

// SSE 提醒监听
function initTaskEvents() {
    const es = new EventSource(API_TASKS + '/events?token=' + encodeURIComponent(token));
    es.onmessage = (e) => {
        const ev = JSON.parse(e.data);
        if (ev.type === 'task_remind') {
            // 角标 + 聊天区提示
            showRemind(ev.message);
        }
    };
}
```

- [ ] **Step 4: 在 init() 里调用 loadTasks() + renderMonth() + initTaskEvents()**

- [ ] **Step 5: 手动验证**

Run: 启动服务 `uvicorn app.main:app --host 0.0.0.0 --port 8001`，浏览器打开 `/`：
1. 左侧出现任务面板，4 tab 切换过滤正常
2. 创建任务后列表实时显示，状态色正确
3. 点「工作记录」看到日历视图，翻页/年视图正常，点某天看明细
4. 给任务设定时任务，到点收到 SSE 提醒角标

- [ ] **Step 6: Commit**

```bash
git add app/routers/frontend.py
git commit -m "feat: 前端任务面板 + 日历视图 + SSE 提醒"
```

---

## 自审记录

- **Spec 覆盖**：F1→Task 8（左侧面板）；F2→Task 3+8（4 过滤）；F3→Task 4+7（定时任务）；F4→Task 2+6（切分）；F5→Task 4+8（日历）。数据模型→Task 1。API→Task 5。SSE→Task 7。
- **类型一致性**：`parse_plan_input`/`split_*` 签名在 Task 2 定义、Task 6 使用一致；service 函数签名在 Task 3/4 定义、Task 5/6/7 使用一致；`task_scheduler.add_schedule` 的 dict 结构在 Task 5 调用处与 Task 7 定义处字段一致（`schedule_id/task_id/user_id/trigger_time/action/advance_to/title`）。
- **占位符**：无 TBD/TODO；所有 code step 均含完整代码。
