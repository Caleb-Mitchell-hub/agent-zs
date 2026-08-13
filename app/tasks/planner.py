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
