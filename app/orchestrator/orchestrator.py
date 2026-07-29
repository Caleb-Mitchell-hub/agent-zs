"""Agent Orchestrator - 系统大脑

职责：
- 判断任务类型
- 选择 Agent
- 创建任务
- 管理执行流程
"""

import json
import logging
import uuid
from datetime import datetime
from enum import Enum

from pydantic import BaseModel

from app.agents.data_agent import DataAgent
from app.agents.write_agent import WriteAgent
from app.agents.knowledge_agent import KnowledgeAgent
from app.agents.report_agent import ReportAgent
from app.memory import session_memory
from app.memory.task_memory import task_memory
from app.memory.user_memory import user_memory
from app.adapter.erp_adapter import erp_adapter
from app.gateway.model_gateway import model_gateway

logger = logging.getLogger(__name__)


class TaskType(str, Enum):
    """任务类型"""
    QUERY = "query"
    REPORT = "report"
    CREATE = "create"
    UPDATE = "update"
    KNOWLEDGE = "knowledge"
    UNKNOWN = "unknown"


class TaskState(str, Enum):
    """任务状态"""
    CREATED = "created"
    PLANNING = "planning"
    EXECUTING = "executing"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    FAILED = "failed"


class Task(BaseModel):
    """任务定义"""
    task_id: str
    task_type: TaskType
    state: TaskState = TaskState.CREATED
    agent_name: str = ""
    input: dict = {}
    output: dict = {}
    error: str = None


class Orchestrator:
    """Agent 编排器"""

    def __init__(self):
        self.data_agent = DataAgent()
        self.write_agent = WriteAgent()
        self.knowledge_agent = KnowledgeAgent()
        self.report_agent = ReportAgent()

    async def process(self, user_input: str, session_id: str, user_id: int, tenant_id: int) -> dict:
        """处理用户请求"""
        # 1. 保存用户消息
        await session_memory.add_message(session_id, "user", user_input)

        # 2. 获取上下文
        context = await session_memory.get_context(session_id)
        messages = await session_memory.get_messages(session_id)

        # 3. 意图识别（通过 Model Gateway）
        intent_result = await model_gateway.route_and_call(
            task_type="intent_classify",
            prompt=f"判断用户意图，只返回：query/create/report/knowledge\n用户输入：{user_input}",
        )
        intent = intent_result.get("response", "query").strip().lower()
        task_type = TaskType(intent) if intent in TaskType.__members__.values() else TaskType.QUERY

        # 4. 创建任务
        task = Task(
            task_id=f"task-{uuid.uuid4().hex[:8]}",
            task_type=task_type,
            state=TaskState.PLANNING,
            input={"user_input": user_input, "context": context},
        )

        # 5. 执行任务
        try:
            task.state = TaskState.EXECUTING

            if task_type == TaskType.QUERY:
                task.agent_name = "data_agent"
                result = await self.data_agent.execute(user_input, messages, context, session_id, user_id, tenant_id)
            elif task_type == TaskType.CREATE:
                task.agent_name = "write_agent"
                result = await self.write_agent.execute(user_input, messages, context, session_id, user_id, tenant_id)
                # 写操作通过 ERP Adapter
                if result.get("status") == "ok" and result.get("doc_id"):
                    await erp_adapter.create_document(
                        doc_type=result.get("doc_type", "unknown"),
                        params=result.get("params", {}),
                        idempotency_key=f"{task.task_id}",
                        user_id=str(user_id),
                        tenant_id=str(tenant_id),
                    )
            elif task_type == TaskType.KNOWLEDGE:
                task.agent_name = "knowledge_agent"
                result = await self.knowledge_agent.execute(user_input, messages, context, session_id, user_id, tenant_id)
            elif task_type == TaskType.REPORT:
                task.agent_name = "report_agent"
                result = await self.report_agent.execute(user_input, messages, context, session_id, user_id, tenant_id)
            else:
                result = {"status": "error", "message": "暂不支持该类型的操作", "error_code": "UNSUPPORTED_TASK"}

            task.output = result
            task.state = TaskState.COMPLETED if result.get("status") == "ok" else TaskState.FAILED

        except Exception as e:
            logger.error(f"任务执行失败: {e}", exc_info=True)
            task.state = TaskState.FAILED
            task.error = str(e)
            result = {"status": "error", "message": str(e), "error_code": "EXECUTION_ERROR"}

        # 6. 保存任务历史
        await task_memory.save_task(
            task_id=task.task_id, session_id=session_id, user_id=user_id,
            tenant_id=tenant_id, task_type=task.task_type.value,
            agent_name=task.agent_name, input_data=task.input,
            output_data=task.output, status=task.state.value,
        )

        # 7. 保存助手回复
        await session_memory.add_message(session_id, "assistant", result.get("message", ""))

        # 8. 更新用户最近查询
        if task_type in [TaskType.QUERY, TaskType.REPORT]:
            await user_memory.add_recent_query(user_id=user_id, query=user_input, sql=result.get("sql", ""))

        return result
