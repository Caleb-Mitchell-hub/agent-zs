"""查询端点 - 自然语言查询"""

import logging
import uuid

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from app.models.schemas import QueryRequest, QueryResponse
from app.gateway.auth import verify_token
from app.gateway.rate_limit import check_rate_limit
from app.orchestrator.orchestrator import Orchestrator

logger = logging.getLogger(__name__)
router = APIRouter()

# 编排器实例
orchestrator = Orchestrator()


@router.post("/query", response_model=QueryResponse)
async def natural_language_query(
    req: QueryRequest,
    request: Request,
    user_info: dict = Depends(verify_token),
    _: None = Depends(check_rate_limit),
):
    """自然语言查询入口

    接收用户自然语言问题，通过 Orchestrator 路由到对应的 Agent 处理。
    """
    # 生成会话 ID（如果没有提供）
    session_id = req.session_id or str(uuid.uuid4())

    logger.info(f"用户 {user_info['user_id']} 查询: {req.question}")

    result = await orchestrator.process(
        user_input=req.question,
        session_id=session_id,
        user_id=user_info["user_id"],
        tenant_id=user_info.get("tenant_id", 1),
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
    """
    import json

    async def event_generator():
        # 生成会话 ID
        session_id = str(uuid.uuid4())

        yield json.dumps({"type": "progress", "message": "正在分析问题..."}, ensure_ascii=False)

        result = await orchestrator.process(
            user_input=question,
            session_id=session_id,
            user_id=user_info["user_id"],
            tenant_id=user_info.get("tenant_id", 1),
        )

        yield json.dumps({
            "type": "result",
            "data": result,
        }, ensure_ascii=False)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
