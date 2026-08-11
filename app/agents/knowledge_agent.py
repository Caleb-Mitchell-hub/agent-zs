"""Knowledge Agent - 知识检索 Agent

职责：
- 企业知识检索（向量 + 关键词混合检索）
- RAG 生成回答（检索 + LLM 总结）
- 知识库无结果时 LLM 兜底回答
"""

import logging
from typing import Optional

from app.tools.search_tool import SearchTool
from app.agent.llm_client import llm_client
from app.memory import session_memory

logger = logging.getLogger(__name__)

# 知识问答 Prompt（有检索结果时）
RAG_PROMPT = """你是一个企业 AI 助手。根据知识库中检索到的内容回答用户问题。

【对话上下文】
{context_block}

【回答规则】
1. 优先基于下面的知识库内容回答
2. 如果知识库内容能完全覆盖用户问题，直接基于知识库回答
3. 如果知识库内容只能部分覆盖，先用知识库内容回答，再补充你的通用知识，并明确标注来源
4. 回答要简洁、结构化，方便用户阅读
5. 如果用户问的是操作步骤，按步骤编号列出
6. 如果对话上下文中有之前的查询结果且用户当前在追问，结合上下文理解用户意图

【知识库检索结果】
{chunks}

【用户问题】
{user_input}

【回答】"""

# 知识问答 Prompt（无检索结果时，LLM 兜底）
FALLBACK_PROMPT = """你是一个企业 AI 助手，同时也是一个智能客服。用户问了一个问题，但在企业知识库中没有找到相关内容。

【对话上下文】
{context_block}

【重要说明】
- 企业知识库主要包含 ERP、采购、销售、库存、审批等业务相关内容
- 对于知识库未覆盖的通用问题（如产品使用、生活常识等），你可以用自己的通用知识回答
- 如果问题属于企业业务范畴但知识库没有，诚实告知用户"知识库中暂无相关信息"，并建议联系管理员补充

【用户问题】
{user_input}

【回答要求】
- 如果可以用通用知识回答，正常回答，不用刻意强调知识库没有
- 如果问题确实需要企业内部知识才能回答，诚实告知并给出建议
- 保持友好、有帮助的客服语气"""


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
            # 1. 使用 Search Tool 检索知识库
            search_result = await self.search_tool.execute(
                query=user_input,
                top_k=5,
            )

            chunks = search_result.get("chunks", [])

            # 2. 更新上下文
            await session_memory.update_context(session_id, {
                "last_knowledge_query": user_input,
                "last_knowledge_count": len(chunks),
            })

            # 3. 构建对话上下文（历史 + 上一轮数据查询参考）
            context_block = self._build_context_block(messages, context)

            # 4. 根据检索结果选择 Prompt 并生成回答
            if chunks:
                # 有检索结果 → RAG 模式
                chunks_text = "\n\n---\n\n".join([
                    f"【知识片段 {i+1}】标题：{c.get('title', '无标题')}\n内容：{c.get('content', '')}"
                    for i, c in enumerate(chunks)
                ])
                prompt = RAG_PROMPT.format(
                    chunks=chunks_text, user_input=user_input,
                    context_block=context_block,
                )
                response = await llm_client.chat(prompt)
                return {
                    "status": "ok",
                    "data": chunks,
                    "message": response.strip(),
                    "source": "knowledge_base",
                }
            else:
                # 无检索结果 → LLM 兜底回答
                prompt = FALLBACK_PROMPT.format(
                    user_input=user_input,
                    context_block=context_block,
                )
                response = await llm_client.chat(prompt)
                return {
                    "status": "ok",
                    "data": None,
                    "message": response.strip(),
                    "source": "llm_fallback",
                }

        except Exception as e:
            logger.error(f"Knowledge Agent 执行失败: {e}", exc_info=True)
            # 异常时也尝试 LLM 兜底
            try:
                response = await llm_client.chat(
                    f"用户问了以下问题，请作为友好客服回答：\n{user_input}"
                )
                return {
                    "status": "ok",
                    "data": None,
                    "message": response.strip(),
                    "source": "llm_fallback",
                }
            except:
                return {
                    "status": "error",
                    "message": f"知识检索失败: {str(e)}",
                    "error_code": "KNOWLEDGE_AGENT_ERROR",
                }

    @staticmethod
    def _build_context_block(messages: list[dict], context: dict) -> str:
        """构建对话上下文块，注入知识问答 prompt。

        包括：最近对话历史 + 上一轮数据查询结果（如果存在）。
        """
        parts = []

        # 对话历史
        if messages:
            recent = messages[-10:]
            history = "\n".join([
                f"{'用户' if m['role'] == 'user' else 'AI'}: {m['content'][:300]}"
                for m in recent
            ])
            parts.append(f"最近对话:\n{history}")

        # 上一轮数据查询参考
        last_result = context.get("last_result")
        if last_result and isinstance(last_result, dict):
            last_query = context.get("last_query", "")
            data = last_result.get("data") or []
            if last_query:
                parts.append(
                    f"上一轮查询: {last_query}\n"
                    f"结果({len(data)}条): {str(data[:3])[:500]}"
                )

        if not parts:
            return "（无对话上下文）"

        return "\n\n".join(parts)
