"""查询端点 - 自然语言查询"""

import logging
import uuid

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from app.models.schemas import QueryRequest, QueryResponse
from app.gateway.auth import verify_token
from app.gateway.rate_limit import check_rate_limit
from app.orchestrator.orchestrator import Orchestrator
from app.services import session_service

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

    user_id = user_info["user_id"]
    tenant_id = user_info.get("tenant_id", 1)

    logger.info(f"用户 {user_id} 查询: {req.question}")

    # 提取用户数据权限（行级安全）
    user_permissions = {
        "warehouse_ids": user_info.get("warehouse_ids", []),
        "region_ids": user_info.get("region_ids", []),
        "customer_ids": user_info.get("customer_ids", []),
        "product_ids": user_info.get("product_ids", []),
    }

    # 持久化：确保会话存在 & 保存用户消息
    try:
        await session_service.ensure_session(session_id, user_id, tenant_id)
        await session_service.save_message(session_id, "user", req.question)
    except Exception as e:
        logger.warning(f"持久化消息失败（非致命）: {e}")

    result = await orchestrator.process(
        user_input=req.question,
        session_id=session_id,
        user_id=user_id,
        tenant_id=tenant_id,
        intent=req.intent,
        user_permissions=user_permissions,
    )

    # 持久化：保存助手回复
    try:
        reply_text = result.get("message") or ""
        if result.get("data"):
            import json
            reply_text = json.dumps(result.get("data"), ensure_ascii=False)
            if result.get("message"):
                reply_text = result["message"] + "\n" + reply_text
        elif result.get("sql"):
            reply_text = f"[SQL] {result['sql']}"
        await session_service.save_message(session_id, "assistant", reply_text)
    except Exception as e:
        logger.warning(f"持久化助手消息失败（非致命）: {e}")

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
            user_permissions={
                "warehouse_ids": user_info.get("warehouse_ids", []),
                "region_ids": user_info.get("region_ids", []),
                "customer_ids": user_info.get("customer_ids", []),
                "product_ids": user_info.get("product_ids", []),
            },
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
