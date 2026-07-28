"""RAG 知识检索工具

支持从知识库中检索相关内容：
- 操作手册
- 业务规则
- 常见问题

使用简单的关键词匹配 + LLM 重排序。
"""

import logging
from sqlalchemy import text
from app.db.session import get_session
from app.agent.llm_client import llm_client

logger = logging.getLogger(__name__)


class RAGResult:
    """RAG 检索结果"""

    def __init__(self, chunks: list[dict], query: str):
        self.chunks = chunks
        self.query = query
        self.count = len(chunks)

    def to_dict(self) -> dict:
        return {
            "chunks": self.chunks,
            "query": self.query,
            "count": self.count,
        }


async def search_knowledge(query: str, top_k: int = 5, category: str = None) -> RAGResult:
    """从知识库检索相关内容

    Args:
        query: 用户查询
        top_k: 返回结果数量
        category: 知识类别（manual, rule, faq, all）

    Returns:
        RAGResult: 检索结果
    """
    try:
        async for session in get_session():
            # 构建查询
            if category and category != "all":
                sql = """
                    SELECT id, title, content, category, tags, relevance_score
                    FROM knowledge_base
                    WHERE category = :category
                    AND (title LIKE :query OR content LIKE :query OR tags LIKE :query)
                    ORDER BY relevance_score DESC
                    LIMIT :top_k
                """
                params = {
                    "category": category,
                    "query": f"%{query}%",
                    "top_k": top_k,
                }
            else:
                sql = """
                    SELECT id, title, content, category, tags, relevance_score
                    FROM knowledge_base
                    WHERE title LIKE :query OR content LIKE :query OR tags LIKE :query
                    ORDER BY relevance_score DESC
                    LIMIT :top_k
                """
                params = {
                    "query": f"%{query}%",
                    "top_k": top_k,
                }

            result = await session.execute(text(sql), params)
            rows = result.mappings().all()

            chunks = []
            for row in rows:
                chunks.append({
                    "id": row["id"],
                    "title": row["title"],
                    "content": row["content"][:500],  # 截断过长内容
                    "category": row["category"],
                    "tags": row["tags"],
                    "score": float(row["relevance_score"]) if row["relevance_score"] else 0,
                })

            # 如果有结果，使用 LLM 重排序
            if chunks and len(chunks) > 1:
                chunks = await _rerank_with_llm(query, chunks)

            logger.info(f"RAG 检索: query='{query}', results={len(chunks)}")

            return RAGResult(chunks=chunks, query=query)

    except Exception as e:
        logger.error(f"RAG 检索失败: {e}", exc_info=True)
        return RAGResult(chunks=[], query=query)


async def _rerank_with_llm(query: str, chunks: list[dict]) -> list[dict]:
    """使用 LLM 对检索结果重排序"""
    try:
        # 构建重排序 prompt
        chunks_text = "\n".join([
            f"{i+1}. [{c['category']}] {c['title']}: {c['content'][:100]}..."
            for i, c in enumerate(chunks)
        ])

        prompt = f"""根据用户查询，对以下知识条目按相关性排序。

用户查询: {query}

知识条目:
{chunks_text}

请返回排序后的编号（用逗号分隔），例如: 2,1,3,5,4
只返回编号，不要解释。"""

        response = await llm_client.chat(prompt)

        # 解析排序结果
        try:
            order = [int(x.strip()) - 1 for x in response.split(",")]
            # 按新顺序重排
            reordered = []
            for idx in order:
                if 0 <= idx < len(chunks):
                    reordered.append(chunks[idx])
            return reordered if reordered else chunks
        except:
            return chunks

    except Exception as e:
        logger.warning(f"LLM 重排序失败: {e}")
        return chunks


async def add_knowledge(
    title: str,
    content: str,
    category: str,
    tags: str = None,
    relevance_score: float = 1.0,
) -> dict:
    """添加知识条目

    Args:
        title: 标题
        content: 内容
        category: 类别 (manual, rule, faq)
        tags: 标签（逗号分隔）
        relevance_score: 相关性分数（用于排序）

    Returns:
        dict: 添加结果
    """
    try:
        async for session in get_session():
            await session.execute(
                text("""
                    INSERT INTO knowledge_base (title, content, category, tags, relevance_score, created_at)
                    VALUES (:title, :content, :category, :tags, :relevance_score, NOW())
                """),
                {
                    "title": title,
                    "content": content,
                    "category": category,
                    "tags": tags,
                    "relevance_score": relevance_score,
                },
            )
            await session.commit()

            logger.info(f"知识条目添加成功: {title}")

            return {
                "status": "ok",
                "message": f"知识条目添加成功: {title}",
            }

    except Exception as e:
        logger.error(f"知识条目添加失败: {e}", exc_info=True)
        return {
            "status": "error",
            "message": f"知识条目添加失败: {str(e)}",
        }


async def get_knowledge_categories() -> list[str]:
    """获取知识库类别列表"""
    try:
        async for session in get_session():
            result = await session.execute(
                text("SELECT DISTINCT category FROM knowledge_base ORDER BY category")
            )
            rows = result.fetchall()
            return [row[0] for row in rows]

    except Exception as e:
        logger.error(f"获取知识库类别失败: {e}", exc_info=True)
        return []
