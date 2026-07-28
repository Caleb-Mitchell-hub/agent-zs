"""Agent Orchestrator - 系统大脑

职责：
- 判断任务类型
- 选择 Agent
- 创建任务
- 管理执行流程
"""

import logging
from enum import Enum
from typing import Optional
from pydantic import BaseModel

from app.agents.data_agent import DataAgent
from app.agents.write_agent import WriteAgent
from app.memory import session_memory
from app.memory.task_memory import task_memory
from app.memory.user_memory import user_memory

logger = logging.getLogger(__name__)


class TaskType(str, Enum):
    """任务类型"""
    QUERY = "query"           # 数据查询
    REPORT = "report"         # 报表生成
    CREATE = "create"         # 创建单据
    UPDATE = "update"         # 更新单据
    KNOWLEDGE = "knowledge"   # 知识检索
    UNKNOWN = "unknown"       # 未知


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
    error: Optional[str] = None


# 意图识别 Prompt
INTENT_PROMPT = """你是一个意图识别专家。根据用户的输入，判断用户想要做什么。

## 用户输入
{user_input}

## 可选意图
- query: 查询数据、统计、分析
- report: 生成报表、图表
- create: 创建单据（采购订单、销售订单等）
- update: 更新单据状态
- knowledge: 查询知识、操作手册、业务规则

## 输出格式
只返回意图类型，不要解释。例如: query"""


class Orchestrator:
    """Agent 编排器"""

    def __init__(self):
        self.data_agent = DataAgent()
        self.write_agent = WriteAgent()

    async def process(self, user_input: str, session_id: str, user_id: int, tenant_id: int) -> dict:
        """处理用户请求

        Args:
            user_input: 用户输入
            session_id: 会话 ID
            user_id: 用户 ID
            tenant_id: 租户 ID

        Returns:
            dict: 处理结果
        """
        # 1. 保存用户消息
        await session_memory.add_message(session_id, "user", user_input)

        # 2. 获取会话上下文
        context = await session_memory.get_context(session_id)
        messages = await session_memory.get_messages(session_id)

        # 3. 识别意图
        task_type = await self._identify_intent(user_input, messages)
        logger.info(f"识别意图: {task_type}")

        # 4. 创建任务
        task = Task(
            task_id=f"task-{session_id}-{len(messages)}",
            task_type=task_type,
            state=TaskState.PLANNING,
            input={"user_input": user_input, "context": context},
        )

        # 5. 更新任务状态
        await session_memory.update_task_state(session_id, task.model_dump())

        # 6. 选择 Agent 执行
        try:
            task.state = TaskState.EXECUTING
            await session_memory.update_task_state(session_id, task.model_dump())

            if task_type in [TaskType.QUERY, TaskType.REPORT]:
                result = await self.data_agent.execute(
                    user_input=user_input,
                    messages=messages,
                    context=context,
                    session_id=session_id,
                    user_id=user_id,
                    tenant_id=tenant_id,
                )
                task.agent_name = "data_agent"
            elif task_type in [TaskType.CREATE, TaskType.UPDATE]:
                result = await self.write_agent.execute(
                    user_input=user_input,
                    messages=messages,
                    context=context,
                    session_id=session_id,
                    user_id=user_id,
                    tenant_id=tenant_id,
                )
                task.agent_name = "write_agent"
            else:
                result = {
                    "status": "error",
                    "message": "暂不支持该类型的操作",
                    "error_code": "UNSUPPORTED_TASK",
                }

            # 7. 更新任务状态
            task.output = result
            task.state = TaskState.COMPLETED if result.get("status") == "ok" else TaskState.FAILED
            task.error = result.get("message") if result.get("status") != "ok" else None

        except Exception as e:
            logger.error(f"任务执行失败: {e}", exc_info=True)
            task.state = TaskState.FAILED
            task.error = str(e)
            result = {
                "status": "error",
                "message": f"任务执行失败: {str(e)}",
                "error_code": "EXECUTION_ERROR",
            }

        # 8. 保存任务状态
        await session_memory.update_task_state(session_id, task.model_dump())

        # 9. 保存任务历史
        await task_memory.save_task(
            task_id=task.task_id,
            session_id=session_id,
            user_id=user_id,
            tenant_id=tenant_id,
            task_type=task.task_type.value,
            agent_name=task.agent_name,
            input_data=task.input,
            output_data=task.output,
            status=task.state.value,
            error_message=task.error,
        )

        # 10. 保存助手回复
        await session_memory.add_message(session_id, "assistant", result.get("message", ""))

        # 11. 更新用户最近查询
        if task_type in [TaskType.QUERY, TaskType.REPORT]:
            await user_memory.add_recent_query(
                user_id=user_id,
                query=user_input,
                sql=result.get("sql", ""),
            )

        return result

    async def _identify_intent(self, user_input: str, messages: list[dict]) -> TaskType:
        """识别用户意图

        Args:
            user_input: 用户输入
            messages: 历史消息

        Returns:
            TaskType: 任务类型
        """
        # 简单的关键词匹配（后续可以用 LLM 优化）
        user_input_lower = user_input.lower()

        # 查询相关
        query_keywords = ["查询", "查", "统计", "分析", "多少", "几个", "哪些", "排名", "排行"]
        if any(kw in user_input_lower for kw in query_keywords):
            return TaskType.QUERY

        # 报表相关
        report_keywords = ["报表", "报告", "图表", "可视化", "趋势"]
        if any(kw in user_input_lower for kw in report_keywords):
            return TaskType.REPORT

        # 创建单据相关
        create_keywords = ["创建", "新建", "添加", "录入", "下单"]
        if any(kw in user_input_lower for kw in create_keywords):
            return TaskType.CREATE

        # 更新单据相关
        update_keywords = ["更新", "修改", "审批", "提交", "驳回"]
        if any(kw in user_input_lower for kw in update_keywords):
            return TaskType.UPDATE

        # 知识检索相关
        knowledge_keywords = ["知识", "手册", "规则", "怎么", "如何", "教程"]
        if any(kw in user_input_lower for kw in knowledge_keywords):
            return TaskType.KNOWLEDGE

        # 默认为查询
        return TaskType.QUERY
