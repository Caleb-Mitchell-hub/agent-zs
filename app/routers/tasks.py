"""任务管理器路由（CRUD / leaves / worklog 端点由 Task 5 追加，此处仅 SSE 订阅）"""
import asyncio
import json
import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from app.gateway.auth import verify_token

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/tasks/events")
async def task_events(request: Request, user_info: dict = Depends(verify_token)):
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
