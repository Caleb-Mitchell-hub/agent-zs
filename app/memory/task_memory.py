"""Task Memory - 任务执行历史存储

存储任务执行历史：
- SQL 查询记录
- Tool 调用记录
- 中间结果
- 错误信息
"""

import json
import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import text

from app.db.session import get_session

logger = logging.getLogger(__name__)


class TaskMemory:
    """任务记忆存储"""

    async def save_task(
        self,
        task_id: str,
        session_id: str,
        user_id: int,
        tenant_id: int,
        task_type: str,
        agent_name: str,
        input_data: dict,
        output_data: dict,
        status: str,
        error_message: Optional[str] = None,
    ) -> bool:
        """保存任务记录

        Args:
            task_id: 任务 ID
            session_id: 会话 ID
            user_id: 用户 ID
            tenant_id: 租户 ID
            task_type: 任务类型
            agent_name: Agent 名称
            input_data: 输入数据
            output_data: 输出数据
            status: 任务状态
            error_message: 错误信息

        Returns:
            bool: 是否保存成功
        """
        try:
            async for session in get_session():
                await session.execute(
                    text("""
                        INSERT INTO task_history (
                            task_id, session_id, user_id, tenant_id,
                            task_type, agent_name,
                            input_data, output_data,
                            status, error_message,
                            created_at
                        ) VALUES (
                            :task_id, :session_id, :user_id, :tenant_id,
                            :task_type, :agent_name,
                            :input_data, :output_data,
                            :status, :error_message,
                            :created_at
                        )
                    """),
                    {
                        "task_id": task_id,
                        "session_id": session_id,
                        "user_id": user_id,
                        "tenant_id": tenant_id,
                        "task_type": task_type,
                        "agent_name": agent_name,
                        "input_data": json.dumps(input_data, ensure_ascii=False),
                        "output_data": json.dumps(output_data, ensure_ascii=False),
                        "status": status,
                        "error_message": error_message,
                        "created_at": datetime.now(),
                    },
                )
                await session.commit()

                logger.info(f"任务记录保存成功: {task_id}")
                return True

        except Exception as e:
            logger.error(f"任务记录保存失败: {e}", exc_info=True)
            return False

    async def save_tool_call(
        self,
        task_id: str,
        tool_name: str,
        tool_input: dict,
        tool_output: dict,
        duration_ms: int,
        status: str,
    ) -> bool:
        """保存工具调用记录

        Args:
            task_id: 任务 ID
            tool_name: 工具名称
            tool_input: 工具输入
            tool_output: 工具输出
            duration_ms: 执行时间（毫秒）
            status: 调用状态

        Returns:
            bool: 是否保存成功
        """
        try:
            async for session in get_session():
                await session.execute(
                    text("""
                        INSERT INTO tool_call_log (
                            task_id, tool_name,
                            tool_input, tool_output,
                            duration_ms, status,
                            created_at
                        ) VALUES (
                            :task_id, :tool_name,
                            :tool_input, :tool_output,
                            :duration_ms, :status,
                            :created_at
                        )
                    """),
                    {
                        "task_id": task_id,
                        "tool_name": tool_name,
                        "tool_input": json.dumps(tool_input, ensure_ascii=False),
                        "tool_output": json.dumps(tool_output, ensure_ascii=False),
                        "duration_ms": duration_ms,
                        "status": status,
                        "created_at": datetime.now(),
                    },
                )
                await session.commit()

                logger.info(f"工具调用记录保存成功: {task_id} - {tool_name}")
                return True

        except Exception as e:
            logger.error(f"工具调用记录保存失败: {e}", exc_info=True)
            return False

    async def get_task_history(
        self,
        user_id: int,
        limit: int = 10,
        task_type: Optional[str] = None,
    ) -> list[dict]:
        """获取任务历史

        Args:
            user_id: 用户 ID
            limit: 返回数量限制
            task_type: 任务类型过滤

        Returns:
            list[dict]: 任务历史列表
        """
        try:
            async for session in get_session():
                if task_type:
                    result = await session.execute(
                        text("""
                            SELECT * FROM task_history
                            WHERE user_id = :user_id AND task_type = :task_type
                            ORDER BY created_at DESC
                            LIMIT :limit
                        """),
                        {"user_id": user_id, "task_type": task_type, "limit": limit},
                    )
                else:
                    result = await session.execute(
                        text("""
                            SELECT * FROM task_history
                            WHERE user_id = :user_id
                            ORDER BY created_at DESC
                            LIMIT :limit
                        """),
                        {"user_id": user_id, "limit": limit},
                    )

                rows = result.mappings().all()
                return [dict(row) for row in rows]

        except Exception as e:
            logger.error(f"获取任务历史失败: {e}", exc_info=True)
            return []


# 全局实例
task_memory = TaskMemory()
