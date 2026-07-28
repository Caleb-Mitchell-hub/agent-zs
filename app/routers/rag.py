"""RAG 知识检索端点"""

import logging
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.gateway.auth import verify_token
from app.gateway.rate_limit import check_rate_limit
from app.tools.rag_tool import search_knowledge, add_knowledge, get_knowledge_categories

logger = logging.getLogger(__name__)
router = APIRouter()


class RAGQueryRequest(BaseModel):
    """RAG 查询请求"""
    query: str
    top_k: int = 5
    category: str | None = None  # manual, rule, faq, all


class RAGQueryResponse(BaseModel):
    """RAG 查询响应"""
    status: str
    chunks: list[dict] | None = None
    query: str | None = None
    count: int | None = None
    message: str | None = None


class AddKnowledgeRequest(BaseModel):
    """添加知识请求"""
    title: str
    content: str
    category: str  # manual, rule, faq
    tags: str | None = None
    relevance_score: float = 1.0


@router.post("/rag/search", response_model=RAGQueryResponse)
async def search(
    req: RAGQueryRequest,
    user_info: dict = Depends(verify_token),
    _: None = Depends(check_rate_limit),
):
    """知识库检索

    从知识库中检索相关内容：
    - manual: 操作手册
    - rule: 业务规则
    - faq: 常见问题
    """
    logger.info(f"用户 {user_info['user_id']} RAG 检索: {req.query}")

    result = await search_knowledge(
        query=req.query,
        top_k=req.top_k,
        category=req.category,
    )

    return RAGQueryResponse(
        status="ok",
        chunks=result.chunks,
        query=result.query,
        count=result.count,
    )


@router.post("/rag/knowledge")
async def add(
    req: AddKnowledgeRequest,
    user_info: dict = Depends(verify_token),
):
    """添加知识条目

    添加新的知识库条目：
    - manual: 操作手册
    - rule: 业务规则
    - faq: 常见问题
    """
    logger.info(f"用户 {user_info['user_id']} 添加知识: {req.title}")

    result = await add_knowledge(
        title=req.title,
        content=req.content,
        category=req.category,
        tags=req.tags,
        relevance_score=req.relevance_score,
    )

    return result


@router.get("/rag/categories")
async def categories():
    """获取知识库类别列表"""
    cats = await get_knowledge_categories()
    return {
        "status": "ok",
        "categories": cats,
    }
