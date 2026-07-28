"""Workflow 路由

职责：
- 工作流管理
- 工作流执行
"""

import logging
import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.gateway.auth import verify_token
from app.workflow.engine import workflow_engine

logger = logging.getLogger(__name__)
router = APIRouter()


class WorkflowRequest(BaseModel):
    """工作流执行请求"""
    workflow_id: str
    params: dict = {}


@router.get("/workflow/list")
async def list_workflows():
    """获取所有工作流定义"""
    workflows = workflow_engine.list_workflows()

    return {
        "status": "ok",
        "workflows": workflows,
    }


@router.post("/workflow/execute")
async def execute_workflow(
    req: WorkflowRequest,
    user_info: dict = Depends(verify_token),
):
    """执行工作流"""
    session_id = str(uuid.uuid4())

    logger.info(f"用户 {user_info['user_id']} 执行工作流: {req.workflow_id}")

    result = await workflow_engine.execute_workflow(
        workflow_id=req.workflow_id,
        session_id=session_id,
        user_id=user_info["user_id"],
        tenant_id=user_info.get("tenant_id", 1),
        params=req.params,
    )

    return result


@router.get("/workflow/status/{instance_id}")
async def get_workflow_status(instance_id: str):
    """获取工作流状态"""
    status = workflow_engine.get_workflow_status(instance_id)

    if not status:
        return {"status": "error", "message": "工作流实例不存在"}

    return {
        "status": "ok",
        "workflow": status,
    }
