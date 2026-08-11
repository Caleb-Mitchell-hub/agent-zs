"""会话端点 — 对话列表 / 历史消息 / 删除"""

import logging

from fastapi import APIRouter, Depends, HTTPException

from app.gateway.auth import verify_token
from app.services import session_service

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/sessions")
async def list_sessions(user_info: dict = Depends(verify_token)):
    """获取当前用户的会话列表

    按最后活跃时间倒序，返回最近 50 条对话。
    """
    user_id = user_info["user_id"]
    sessions = await session_service.list_user_sessions(user_id)
    return {"status": "ok", "sessions": sessions}


@router.get("/sessions/{session_id}/messages")
async def get_messages(session_id: str, user_info: dict = Depends(verify_token)):
    """获取指定会话的消息历史

    返回该会话的所有消息（最多 200 条）。
    """
    messages = await session_service.get_session_messages(session_id)
    return {"status": "ok", "session_id": session_id, "messages": messages}


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str, user_info: dict = Depends(verify_token)):
    """删除（归档）指定会话

    软删除：标记为 archived，不物理删除数据。
    """
    user_id = user_info["user_id"]
    ok = await session_service.delete_session(session_id, user_id)
    if not ok:
        raise HTTPException(status_code=404, detail="会话不存在或无权操作")
    return {"status": "ok", "message": "会话已删除"}
