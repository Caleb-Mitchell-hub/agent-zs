"""任务定时调度器（APScheduler AsyncIOScheduler）+ SSE 推送 pub/sub"""
import asyncio
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.tasks.service import list_pending_schedules, list_missed_schedules, mark_schedule_fired, advance_task

logger = logging.getLogger(__name__)


class TaskScheduler:
    """定时任务调度 + 按 user_id 的 SSE 订阅推送"""

    def __init__(self):
        self._scheduler: AsyncIOScheduler | None = None
        self._subscribers: dict[int, set[asyncio.Queue]] = {}

    async def start(self):
        """启动调度器并加载未触发任务，补发停机期间错过的提醒"""
        if self._scheduler is not None:
            return
        self._scheduler = AsyncIOScheduler()
        self._scheduler.start()
        scheds = await list_pending_schedules()
        for s in scheds:
            self._add_job(s)
        logger.info(f"任务调度器启动，加载 {len(scheds)} 个定时任务")
        # 补发停机期间到点但未触发的定时任务
        missed = await list_missed_schedules()
        for s in missed:
            await self._fire(s)
        if missed:
            logger.warning(f"补发 {len(missed)} 个停机期间错过的定时任务提醒")

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
