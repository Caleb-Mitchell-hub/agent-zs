"""RAG 知识检索工具

支持从知识库中检索相关内容：
- 操作手册
- 业务规则
- 常见问题

使用关键词匹配 + 确定性分数排序。
"""

import logging
import re
from sqlalchemy import text
from app.db.session import get_session

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

            # 如果有结果，使用确定性分数排序
            if chunks and len(chunks) > 1:
                chunks = sorted(
                    chunks,
                    key=lambda c: _score_chunk(query, c),
                    reverse=True,
                )[:top_k]

            logger.info(f"RAG 检索: query='{query}', results={len(chunks)}")

            return RAGResult(chunks=chunks, query=query)

    except Exception as e:
        logger.error(f"RAG 检索失败: {e}", exc_info=True)
        return RAGResult(chunks=[], query=query)


def _split_keywords(query: str) -> list[str]:
    """将查询切分为关键词列表：按空格/逗号切分，并额外加入整个查询。"""
    keywords = [kw for kw in re.split(r"[,，\s]+", query) if kw]
    if query and query not in keywords:
        keywords.append(query)
    return keywords


def _score_chunk(query: str, chunk: dict) -> float:
    """确定性相关性评分：relevance_score * 0.5 + 关键词重合度。

    关键词重合度 = 查询关键词中出现在 chunk 标题或内容里的个数。
    """
    keywords = _split_keywords(query)
    title = chunk.get("title") or ""
    content = chunk.get("content") or ""
    overlap = sum(1 for kw in keywords if kw in title or kw in content)
    return float(chunk.get("score", 0)) * 0.5 + float(overlap)


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
