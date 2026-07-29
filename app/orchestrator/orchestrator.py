"""Agent Orchestrator - 系统大脑

职责：
- 意图理解（两级机制）
- 任务规划
- 选择 Agent
- 管理执行流程
- 安全防护
"""

import json
import logging
import re
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
from app.memory.extractor import memory_extractor
from app.adapter.erp_adapter import erp_adapter
from app.gateway.model_gateway import model_gateway
from app.security.prompt_guard import prompt_guard
from app.security.data_masking import data_masking
from app.security.circuit_breaker import circuit_breaker_manager
from app.orchestrator.planner import planner
from app.tools.registry import tool_registry

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

        # 0. 安全检查：Prompt 注入防护
        safety_check = prompt_guard.check_input(user_input)
        if not safety_check["safe"]:
            logger.warning(f"检测到注入威胁: {safety_check['threats']}")
            return {"status": "error", "message": "输入包含不安全内容", "error_code": "UNSAFE_INPUT"}

        # 1. 清理输入
        clean_input = prompt_guard.sanitize_input(user_input)

        # 2. 保存用户消息
        await session_memory.add_message(session_id, "user", clean_input)

        # 3. 获取上下文
        context = await session_memory.get_context(session_id)
        messages = await session_memory.get_messages(session_id)

        # 4. 意图识别（两级机制）
        intent = await planner.classify_intent(clean_input)
        task_type = TaskType(intent) if intent in [t.value for t in TaskType] else TaskType.QUERY

        # 5. 创建任务
        task = Task(
            task_id=f"task-{uuid.uuid4().hex[:8]}",
            task_type=task_type,
            state=TaskState.PLANNING,
            input={"user_input": clean_input, "context": context},
        )

        # 6. 执行任务（带熔断保护）
        try:
            task.state = TaskState.EXECUTING

            if task_type == TaskType.QUERY:
                task.agent_name = "data_agent"
                if not circuit_breaker_manager.can_execute("data_agent"):
                    return {"status": "error", "message": "查询服务暂时不可用", "error_code": "CIRCUIT_OPEN"}
                result = await self.data_agent.execute(clean_input, messages, context, session_id, user_id, tenant_id)
                circuit_breaker_manager.record_success("data_agent")

            elif task_type == TaskType.CREATE:
                task.agent_name = "write_agent"
                if not circuit_breaker_manager.can_execute("write_agent"):
                    return {"status": "error", "message": "创建服务暂时不可用", "error_code": "CIRCUIT_OPEN"}
                result = await self.write_agent.execute(clean_input, messages, context, session_id, user_id, tenant_id)
                circuit_breaker_manager.record_success("write_agent")

            elif task_type == TaskType.KNOWLEDGE:
                task.agent_name = "knowledge_agent"
                if not circuit_breaker_manager.can_execute("knowledge_agent"):
                    return {"status": "error", "message": "知识服务暂时不可用", "error_code": "CIRCUIT_OPEN"}
                result = await self.knowledge_agent.execute(clean_input, messages, context, session_id, user_id, tenant_id)
                circuit_breaker_manager.record_success("knowledge_agent")

            elif task_type == TaskType.REPORT:
                task.agent_name = "report_agent"
                if not circuit_breaker_manager.can_execute("report_agent"):
                    return {"status": "error", "message": "报表服务暂时不可用", "error_code": "CIRCUIT_OPEN"}
                result = await self.report_agent.execute(clean_input, messages, context, session_id, user_id, tenant_id)
                circuit_breaker_manager.record_success("report_agent")

            else:
                result = {"status": "error", "message": "暂不支持该类型的操作", "error_code": "UNSUPPORTED_TASK"}

            task.output = result
            task.state = TaskState.COMPLETED if result.get("status") == "ok" else TaskState.FAILED

        except Exception as e:
            logger.error(f"任务执行失败: {e}", exc_info=True)
            task.state = TaskState.FAILED
            task.error = str(e)
            result = {"status": "error", "message": str(e), "error_code": "EXECUTION_ERROR"}

            # 记录失败（触发熔断）
            if task.agent_name:
                circuit_breaker_manager.record_failure(task.agent_name)

        # 7. 保存任务历史
        await task_memory.save_task(
            task_id=task.task_id, session_id=session_id, user_id=user_id,
            tenant_id=tenant_id, task_type=task.task_type.value,
            agent_name=task.agent_name, input_data=task.input,
            output_data=task.output, status=task.state.value,
        )

        # 8. 保存助手回复
        await session_memory.add_message(session_id, "assistant", result.get("message", ""))

        # 9. 记忆抽取
        if await memory_extractor.should_extract(messages):
            conversation = "\n".join([f"{m['role']}: {m['content']}" for m in messages[-10:]])
            await memory_extractor.extract_and_save(conversation, str(user_id), str(tenant_id), session_id)

        # 10. 脱敏处理（日志）
        masked_result = data_masking.mask_for_log(result)
        logger.info(f"任务完成: {task.task_id}, 状态: {task.state.value}")

        return result
