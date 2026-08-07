"""Agent Orchestrator - 系统大脑

基于 LangGraph 图编排：
- 意图理解（规则引擎优先，LLM 兜底）
- 任务规划
- 选择 Agent
- 管理执行流程
- 安全防护

图结构见 app/orchestrator/langgraph_flow.py，节点严格区分确定性/LLM。
对外保持 process() 签名不变，路由层无需改动。
"""

import logging
import uuid
from enum import Enum

from pydantic import BaseModel

from app.security.tracing import generate_trace_id, set_trace_id
from app.orchestrator.langgraph_flow import get_graph

logger = logging.getLogger(__name__)


class TaskType(str, Enum):
    """任务类型"""
    QUERY = "query"
    REPORT = "report"
    CREATE = "create"
    UPDATE = "update"
    KNOWLEDGE = "knowledge"
    MEMORY = "memory"
    CHAT = "chat"
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
        self.graph = get_graph()

    async def process(
        self,
        user_input: str,
        session_id: str,
        user_id: int,
        tenant_id: int,
        intent: str = None,
    ) -> dict:
        """处理用户请求（基于 LangGraph 图执行）

        Args:
            user_input: 用户输入
            session_id: 会话 ID
            user_id: 用户 ID
            tenant_id: 租户 ID
            intent: 前端直达意图（可选，快捷按钮直接携带，跳过分类）

        Returns:
            dict: 执行结果
        """
        # 生成 trace_id，贯穿全链路
        trace_id = generate_trace_id()
        set_trace_id(trace_id)

        # 从 Redis 加载会话历史
        from app.memory.session_memory import get_messages, get_context
        messages = await get_messages(session_id)
        context = await get_context(session_id)

        # 初始状态
        state = {
            "user_input": user_input,
            "session_id": session_id,
            "user_id": user_id,
            "tenant_id": tenant_id,
            "intent": intent,
            "trace_id": trace_id,
            "messages": messages,
            "context": context,
        }

        try:
            result = await self.graph.ainvoke(state)
            return result.get("result") or {
                "status": "error",
                "message": "编排执行未返回结果",
                "error_code": "EMPTY_RESULT",
            }
        except Exception as e:
            logger.error(f"编排执行失败: {e}", exc_info=True)
            return {"status": "error", "message": str(e), "error_code": "EXECUTION_ERROR"}
