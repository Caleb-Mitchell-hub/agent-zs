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


def _data_to_markdown(data: list[dict]) -> str:
    """将查询结果转为标准 Markdown 表格文本。

    用于持久化助手消息与前端复制，保证历史回看、复制、实时展示格式一致。
    """
    if not data:
        return ""
    keys = list(data[0].keys())
    lines = [
        "| " + " | ".join(str(k) for k in keys) + " |",
        "| " + " | ".join(["---"] * len(keys)) + " |",
    ]
    for row in data:
        cells = []
        for k in keys:
            v = row.get(k)
            cell = "" if v is None else str(v).replace("\n", " ")
            cells.append(cell)
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def _build_reply_text(result: dict) -> str:
    """构建助手回复文本：数据用标准 Markdown 表格。

    供复制、实时展示、历史回看共用，保证三处格式一致。
    """
    reply_text = result.get("message") or ""
    if result.get("data"):
        md = _data_to_markdown(result.get("data"))
        reply_text = (result["message"] + "\n\n" + md) if result.get("message") else md
    elif result.get("sql"):
        reply_text = f"[SQL] {result['sql']}"
    return reply_text


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

    # 持久化：保存助手回复（数据用标准 Markdown 表格，历史回看格式不再变化）
    try:
        await session_service.save_message(session_id, "assistant", _build_reply_text(result))
    except Exception as e:
        logger.warning(f"持久化助手消息失败（非致命）: {e}")

    return QueryResponse(**result)


@router.get("/query/stream")
async def natural_language_query_stream(
    question: str,
    request: Request,
    user_info: dict = Depends(verify_token),
    _: None = Depends(check_rate_limit),
    session_id: str = "",
    intent: str = "",
):
    """SSE 流式查询 — 分阶段实时输出查询进度，最后返回结果

    图执行期间通过 progress_callback 把各阶段进度推送给客户端；
    结果结构与 POST /query 一致，前端按标准 Markdown 渲染。
    """
    import asyncio
    import json

    user_id = user_info["user_id"]
    tenant_id = user_info.get("tenant_id", 1)
    sid = session_id or str(uuid.uuid4())

    # 提取用户数据权限（行级安全）
    user_permissions = {
        "warehouse_ids": user_info.get("warehouse_ids", []),
        "region_ids": user_info.get("region_ids", []),
        "customer_ids": user_info.get("customer_ids", []),
        "product_ids": user_info.get("product_ids", []),
    }

    async def event_generator():
        # 持久化：确保会话存在 & 保存用户消息
        try:
            await session_service.ensure_session(sid, user_id, tenant_id)
            await session_service.save_message(sid, "user", question)
        except Exception as e:
            logger.warning(f"持久化用户消息失败（非致命）: {e}")

        # 队列：图执行期间，进度回调把事件放入队列，生成器逐条以 SSE 推送
        queue: asyncio.Queue = asyncio.Queue()

        async def progress(message: str) -> None:
            """进度回调，由图节点调用"""
            await queue.put({"type": "progress", "message": message})

        async def run() -> None:
            """后台执行编排，完成后放入结果事件，最后放结束哨兵"""
            try:
                result = await orchestrator.process(
                    user_input=question,
                    session_id=sid,
                    user_id=user_id,
                    tenant_id=tenant_id,
                    intent=intent or None,
                    user_permissions=user_permissions,
                    progress_callback=progress,
                )
                # 持久化：保存助手回复（数据用标准 Markdown 表格，与 POST /query 一致）
                try:
                    await session_service.save_message(sid, "assistant", _build_reply_text(result))
                except Exception as e:
                    logger.warning(f"持久化助手消息失败（非致命）: {e}")
                await queue.put({"type": "result", "data": result})
            except Exception as e:
                logger.error(f"流式查询执行失败: {e}", exc_info=True)
                await queue.put({
                    "type": "result",
                    "data": {"status": "error", "message": f"查询执行失败: {e}", "error_code": "EXECUTION_ERROR"},
                })
            finally:
                # 结束哨兵：通知主循环停止，SSE 响应正常关闭
                await queue.put(None)

        task = asyncio.create_task(run())
        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                # 客户端已断开则停止推送
                if await request.is_disconnected():
                    task.cancel()
                    break
                yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"
                await asyncio.sleep(0)
        finally:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
