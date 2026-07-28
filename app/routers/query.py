"""查询端点 - 自然语言查询转 SQL"""

import json
import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from app.models.schemas import QueryRequest, QueryResponse
from app.agent.orchestrator import QueryOrchestrator
from app.gateway.auth import verify_token
from app.gateway.rate_limit import check_rate_limit

logger = logging.getLogger(__name__)
router = APIRouter()

# 编排器实例
query_orchestrator = QueryOrchestrator()


@router.post("/query", response_model=QueryResponse)
async def natural_language_query(
    req: QueryRequest,
    request: Request,
    user_info: dict = Depends(verify_token),
    _: None = Depends(check_rate_limit),
):
    """自然语言查询入口

    接收用户自然语言问题，转为 SQL 查询并返回结果。
    需要认证 token。
    """
    logger.info(f"用户 {user_info['user_id']} 查询: {req.question}")

    result = await query_orchestrator.process_query(
        question=req.question,
        tenant_id=user_info.get("tenant_id"),
    )
    return QueryResponse(**result)


@router.get("/query/stream")
async def natural_language_query_stream(
    question: str,
    request: Request,
    user_info: dict = Depends(verify_token),
    _: None = Depends(check_rate_limit),
):
    """SSE 流式查询

    实时输出查询进度和结果。
    需要认证 token。
    """
    logger.info(f"用户 {user_info['user_id']} 流式查询: {question}")

    async def event_generator():
        async for chunk in query_orchestrator.process_query_stream(question):
            yield f"data: {chunk}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
