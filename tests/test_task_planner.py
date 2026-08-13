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
