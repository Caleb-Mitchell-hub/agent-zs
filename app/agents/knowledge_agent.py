"""Knowledge Agent - 知识检索 Agent

职责：
- 企业知识检索
- RAG (Retrieval Augmented Generation)

架构：
Query → Embedding → Vector DB → Reranker → LLM
"""

import logging
from typing import Optional

from app.tools.search_tool import SearchTool
from app.memory import session_memory

logger = logging.getLogger(__name__)


class KnowledgeAgent:
    """知识检索 Agent"""

    def __init__(self):
        self.search_tool = SearchTool()

    async def execute(
        self,
        user_input: str,
        messages: list[dict],
        context: dict,
        session_id: str,
        user_id: int,
        tenant_id: int,
    ) -> dict:
        """执行知识检索任务

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
            # 1. 使用 Search Tool 检索知识
            result = await self.search_tool.execute(
                query=user_input,
                top_k=5,
            )

            # 2. 更新上下文
            await session_memory.update_context(session_id, {
                "last_knowledge_query": user_input,
                "last_knowledge_count": len(result.get("chunks", [])),
            })

            return result

        except Exception as e:
            logger.error(f"Knowledge Agent 执行失败: {e}", exc_info=True)
            return {
                "status": "error",
                "message": f"知识检索失败: {str(e)}",
                "error_code": "KNOWLEDGE_AGENT_ERROR",
            }
