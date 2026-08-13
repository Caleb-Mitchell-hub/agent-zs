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
