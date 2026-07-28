"""Session Memory - Redis 会话存储

存储短期上下文：
- 当前聊天历史
- 当前任务状态
- 用户上下文
"""

import json
import logging
from typing import Optional
import redis.asyncio as redis

from app.config import settings

logger = logging.getLogger(__name__)

# Redis 连接池
_redis_pool: Optional[redis.Redis] = None


async def init_redis():
    """初始化 Redis 连接"""
    global _redis_pool
    _redis_pool = redis.Redis(
        host=settings.redis_host,
        port=settings.redis_port,
        db=settings.redis_db,
        password=settings.redis_password,
        decode_responses=True,
    )
    logger.info(f"Redis 连接初始化完成: {settings.redis_host}:{settings.redis_port}")


async def close_redis():
    """关闭 Redis 连接"""
    global _redis_pool
    if _redis_pool:
        await _redis_pool.close()
        logger.info("Redis 连接已关闭")


def _get_redis() -> redis.Redis:
    """获取 Redis 连接"""
    if _redis_pool is None:
        raise RuntimeError("Redis 未初始化，请先调用 init_redis()")
    return _redis_pool


async def get_session(session_id: str) -> dict:
    """获取会话数据

    Args:
        session_id: 会话 ID

    Returns:
        dict: 会话数据，包含 messages, context, task_state
    """
    r = _get_redis()
    data = await r.get(f"session:{session_id}")
    if data:
        return json.loads(data)
    return {
        "session_id": session_id,
        "messages": [],
        "context": {},
        "task_state": None,
    }


async def save_session(session_id: str, session_data: dict, ttl: int = 3600):
    """保存会话数据

    Args:
        session_id: 会话 ID
        session_data: 会话数据
        ttl: 过期时间（秒），默认 1 小时
    """
    r = _get_redis()
    await r.setex(
        f"session:{session_id}",
        ttl,
        json.dumps(session_data, ensure_ascii=False)
    )


async def add_message(session_id: str, role: str, content: str):
    """添加消息到会话历史

    Args:
        session_id: 会话 ID
        role: 消息角色 (user/assistant/system)
        content: 消息内容
    """
    session = await get_session(session_id)
    session["messages"].append({
        "role": role,
        "content": content,
    })
    # 保留最近 20 条消息
    if len(session["messages"]) > 20:
        session["messages"] = session["messages"][-20:]
    await save_session(session_id, session)


async def get_messages(session_id: str) -> list[dict]:
    """获取会话消息历史

    Args:
        session_id: 会话 ID

    Returns:
        list[dict]: 消息列表
    """
    session = await get_session(session_id)
    return session.get("messages", [])


async def update_context(session_id: str, context: dict):
    """更新会话上下文

    Args:
        session_id: 会话 ID
        context: 上下文数据
    """
    session = await get_session(session_id)
    session["context"].update(context)
    await save_session(session_id, session)


async def get_context(session_id: str) -> dict:
    """获取会话上下文

    Args:
        session_id: 会话 ID

    Returns:
        dict: 上下文数据
    """
    session = await get_session(session_id)
    return session.get("context", {})


async def update_task_state(session_id: str, task_state: dict):
    """更新任务状态

    Args:
        session_id: 会话 ID
        task_state: 任务状态
    """
    session = await get_session(session_id)
    session["task_state"] = task_state
    await save_session(session_id, session)


async def get_task_state(session_id: str) -> Optional[dict]:
    """获取任务状态

    Args:
        session_id: 会话 ID

    Returns:
        Optional[dict]: 任务状态
    """
    session = await get_session(session_id)
    return session.get("task_state")


async def delete_session(session_id: str):
    """删除会话

    Args:
        session_id: 会话 ID
    """
    r = _get_redis()
    await r.delete(f"session:{session_id}")
