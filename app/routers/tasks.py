"""任务管理器路由（SSE 订阅 + 任务 CRUD / 定时任务 / 请假 / 工作记录）"""
import json

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.gateway.auth import verify_token
from app.tasks import service
from app.tasks.schemas import TaskCreate, TaskUpdate, ScheduleCreate, LeaveCreate

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
    """取消定时任务（删 DB 记录并同步取消调度器 job）"""
    sched_id = await service.get_schedule_id(user_info["user_id"], task_id)
    ok = await service.delete_schedule(user_info["user_id"], task_id)
    if not ok:
        raise HTTPException(status_code=404, detail="定时任务不存在")
    if sched_id is not None:
        from app.tasks.scheduler import task_scheduler
        await task_scheduler.remove_schedule(sched_id)
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
