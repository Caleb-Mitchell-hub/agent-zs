"""Workflow 编排引擎

职责：
- 定义工作流
- 执行工作流
- 管理工作流状态
"""

import logging
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel

from app.orchestrator.orchestrator import Orchestrator
from app.memory import session_memory

logger = logging.getLogger(__name__)


class WorkflowStatus(str, Enum):
    """工作流状态"""
    CREATED = "created"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class WorkflowStep(BaseModel):
    """工作流步骤"""
    step_id: str
    name: str
    agent: str  # data_agent, write_agent, knowledge_agent
    action: str
    params: dict = {}
    depends_on: list[str] = []  # 依赖的步骤 ID


class WorkflowDefinition(BaseModel):
    """工作流定义"""
    workflow_id: str
    name: str
    description: str = ""
    steps: list[WorkflowStep]
    created_at: datetime = None


class WorkflowInstance(BaseModel):
    """工作流实例"""
    instance_id: str
    workflow_id: str
    status: WorkflowStatus = WorkflowStatus.CREATED
    current_step: str = ""
    results: dict = {}
    started_at: datetime = None
    completed_at: datetime = None


# 预定义工作流
WORKFLOW_DEFINITIONS = {
    "purchase_order_full": WorkflowDefinition(
        workflow_id="purchase_order_full",
        name="采购订单全流程",
        description="创建采购订单 -> 提交审批 -> 审批通过 -> 入库",
        steps=[
            WorkflowStep(
                step_id="create_order",
                name="创建采购订单",
                agent="write_agent",
                action="create",
                params={"doc_type": "purchase_order"},
            ),
            WorkflowStep(
                step_id="submit_approval",
                name="提交审批",
                agent="write_agent",
                action="submit_approval",
                depends_on=["create_order"],
            ),
            WorkflowStep(
                step_id="approve",
                name="审批",
                agent="write_agent",
                action="approve",
                depends_on=["submit_approval"],
            ),
        ],
    ),
    "sales_report": WorkflowDefinition(
        workflow_id="sales_report",
        name="销售报表生成",
        description="查询销售数据 -> 生成报表 -> 发送通知",
        steps=[
            WorkflowStep(
                step_id="query_sales",
                name="查询销售数据",
                agent="data_agent",
                action="query",
                params={"query": "查询本月销售数据"},
            ),
            WorkflowStep(
                step_id="generate_report",
                name="生成报表",
                agent="data_agent",
                action="report",
                depends_on=["query_sales"],
            ),
        ],
    ),
}


class WorkflowEngine:
    """工作流引擎"""

    def __init__(self):
        self.orchestrator = Orchestrator()
        self._instances: dict[str, WorkflowInstance] = {}

    async def execute_workflow(
        self,
        workflow_id: str,
        session_id: str,
        user_id: int,
        tenant_id: int,
        params: dict = {},
    ) -> dict:
        """执行工作流

        Args:
            workflow_id: 工作流 ID
            session_id: 会话 ID
            user_id: 用户 ID
            tenant_id: 租户 ID
            params: 参数

        Returns:
            dict: 执行结果
        """
        # 获取工作流定义
        workflow_def = WORKFLOW_DEFINITIONS.get(workflow_id)
        if not workflow_def:
            return {"status": "error", "message": f"工作流不存在: {workflow_id}"}

        # 创建工作流实例
        import uuid
        instance_id = str(uuid.uuid4())
        instance = WorkflowInstance(
            instance_id=instance_id,
            workflow_id=workflow_id,
            status=WorkflowStatus.RUNNING,
            started_at=datetime.now(),
        )
        self._instances[instance_id] = instance

        try:
            # 按顺序执行步骤
            for step in workflow_def.steps:
                instance.current_step = step.step_id

                logger.info(f"执行工作流步骤: {step.name}")

                # 执行步骤
                result = await self._execute_step(
                    step=step,
                    session_id=session_id,
                    user_id=user_id,
                    tenant_id=tenant_id,
                    params={**step.params, **params},
                )

                instance.results[step.step_id] = result

                # 检查步骤是否成功
                if result.get("status") != "ok":
                    instance.status = WorkflowStatus.FAILED
                    return {
                        "status": "error",
                        "instance_id": instance_id,
                        "message": f"步骤失败: {step.name}",
                        "results": instance.results,
                    }

            # 工作流完成
            instance.status = WorkflowStatus.COMPLETED
            instance.completed_at = datetime.now()

            logger.info(f"工作流完成: {workflow_id}")

            return {
                "status": "ok",
                "instance_id": instance_id,
                "message": f"工作流执行完成: {workflow_def.name}",
                "results": instance.results,
            }

        except Exception as e:
            instance.status = WorkflowStatus.FAILED
            logger.error(f"工作流执行失败: {e}", exc_info=True)
            return {
                "status": "error",
                "instance_id": instance_id,
                "message": f"工作流执行失败: {str(e)}",
            }

    async def _execute_step(
        self,
        step: WorkflowStep,
        session_id: str,
        user_id: int,
        tenant_id: int,
        params: dict,
    ) -> dict:
        """执行工作流步骤

        Args:
            step: 工作流步骤
            session_id: 会话 ID
            user_id: 用户 ID
            tenant_id: 租户 ID
            params: 参数

        Returns:
            dict: 执行结果
        """
        # 使用 Orchestrator 执行
        user_input = params.get("query", step.name)

        return await self.orchestrator.process(
            user_input=user_input,
            session_id=session_id,
            user_id=user_id,
            tenant_id=tenant_id,
        )

    def get_workflow_status(self, instance_id: str) -> Optional[dict]:
        """获取工作流状态

        Args:
            instance_id: 实例 ID

        Returns:
            Optional[dict]: 工作流状态
        """
        instance = self._instances.get(instance_id)
        if not instance:
            return None

        return {
            "instance_id": instance.instance_id,
            "workflow_id": instance.workflow_id,
            "status": instance.status.value,
            "current_step": instance.current_step,
            "results": instance.results,
            "started_at": str(instance.started_at) if instance.started_at else None,
            "completed_at": str(instance.completed_at) if instance.completed_at else None,
        }

    def list_workflows(self) -> list[dict]:
        """获取所有工作流定义

        Returns:
            list[dict]: 工作流定义列表
        """
        workflows = []
        for wf in WORKFLOW_DEFINITIONS.values():
            workflows.append({
                "workflow_id": wf.workflow_id,
                "name": wf.name,
                "description": wf.description,
                "steps": len(wf.steps),
            })
        return workflows


# 全局实例
workflow_engine = WorkflowEngine()
