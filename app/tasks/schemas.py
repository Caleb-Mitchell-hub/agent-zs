"""任务管理器 Pydantic 模型"""
from datetime import datetime, date
from typing import Literal
from pydantic import BaseModel


class TaskCreate(BaseModel):
    title: str
    deadline: datetime | None = None
    priority: int = 0


class TaskUpdate(BaseModel):
    title: str | None = None
    status: Literal["pending", "doing", "done"] | None = None
    deadline: datetime | None = None
    priority: int | None = None


class TaskPlanItem(BaseModel):
    title: str
    date: str          # "YYYY-MM-DD"
    time: str | None = None  # "HH:MM" 或 None


class TaskPlanCreate(BaseModel):
    items: list[TaskPlanItem]


class ScheduleCreate(BaseModel):
    trigger_time: datetime
    action: Literal["remind", "remind_advance"]
    advance_to: Literal["doing", "done"] | None = None


class LeaveCreate(BaseModel):
    day: date
    note: str | None = None
