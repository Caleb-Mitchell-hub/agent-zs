"""Data Agent - 数据分析 Agent

职责：
- 自然语言查询数据库
- 生成报表

工具：
- Database Tool (NL→SQL)
- Chart Tool (报表生成)
"""

import logging
from typing import Optional

from app.tools.database_tool import DatabaseTool
from app.memory import session_memory

logger = logging.getLogger(__name__)


class DataAgent:
    """数据分析 Agent"""

    def __init__(self):
        self.db_tool = DatabaseTool()

    async def execute(
        self,
        user_input: str,
        messages: list[dict],
        context: dict,
        session_id: str,
        user_id: int,
        tenant_id: int,
    ) -> dict:
        """执行数据分析任务

        Args:
            user_input: 用户输入
            messages: 历史消息
            context: 会话上下文
            session_id: 会话 ID
            user_id: 用户 ID
            tenant_id: 租户 ID

        Returns:
            dict: 执行结果
        """
        try:
            # 1. 使用 Database Tool 执行查询
            result = await self.db_tool.execute(
                query=user_input,
                messages=messages,
                context=context,
            )

            # 2. 更新上下文
            await session_memory.update_context(session_id, {
                "last_query": user_input,
                "last_sql": result.get("sql"),
                "last_result_count": len(result.get("data", [])),
            })

            return result

        except Exception as e:
            logger.error(f"Data Agent 执行失败: {e}", exc_info=True)
            return {
                "status": "error",
                "message": f"查询执行失败: {str(e)}",
                "error_code": "DATA_AGENT_ERROR",
            }
