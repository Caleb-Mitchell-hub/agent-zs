"""会话服务 — MySQL 会话与消息持久化

提供会话列表、消息历史、会话删除等 CRUD 操作。
"""

import logging
import uuid
from datetime import datetime

from sqlalchemy import text

logger = logging.getLogger(__name__)

# 每页最大会话数
MAX_SESSIONS = 50
# 每会话最大消息数
MAX_MESSAGES = 200


def _get_factory():
    """延迟获取数据库会话工厂（避免 import 时捕获 None）"""
    from app.db.session import async_session_factory
    if async_session_factory is None:
        raise RuntimeError("数据库未初始化")
    return async_session_factory


async def _execute_write(sql: str, params: dict = None) -> int:
    """执行写操作，返回影响行数"""
    factory = _get_factory()
    async with factory() as session:
        result = await session.execute(text(sql), params or {})
        await session.commit()
        return result.rowcount


async def _execute_read(sql: str, params: dict = None) -> list[dict]:
    """执行只读查询，返回字典列表"""
    factory = _get_factory()
    async with factory() as session:
        result = await session.execute(text(sql), params or {})
        rows = result.mappings().all()
        return [dict(row) for row in rows]


async def ensure_session(session_id: str, user_id: int, tenant_id: int, channel: str = "web"):
    """创建或更新会话记录

    Args:
        session_id: 会话 ID
        user_id: 用户 ID
        tenant_id: 租户 ID
        channel: 访问渠道
    """
    await _execute_write(
        """
        INSERT INTO sessions (session_id, tenant_id, user_id, channel, status, created_at, last_active_at)
        VALUES (:sid, :tid, :uid, :ch, 'active', NOW(), NOW())
        ON DUPLICATE KEY UPDATE last_active_at = NOW(), status = 'active'
        """,
        {"sid": session_id, "tid": str(tenant_id), "uid": str(user_id), "ch": channel},
    )


async def save_message(session_id: str, role: str, content: str, trace_id: str = None) -> str:
    """保存一条消息

    Args:
        session_id: 会话 ID
        role: 消息角色 (user/assistant/tool)
        content: 消息内容
        trace_id: 追踪 ID

    Returns:
        str: 消息 ID
    """
    message_id = str(uuid.uuid4())
    await _execute_write(
        """
        INSERT INTO messages (message_id, session_id, role, content, trace_id, created_at)
        VALUES (:mid, :sid, :role, :content, :tid, NOW())
        """,
        {"mid": message_id, "sid": session_id, "role": role, "content": content or "", "tid": trace_id or ""},
    )
    return message_id


async def list_user_sessions(user_id: int, limit: int = MAX_SESSIONS) -> list[dict]:
    """获取用户的会话列表（按最后活跃时间倒序，附带第一条用户消息作为标题）

    Args:
        user_id: 用户 ID
        limit: 返回数量上限

    Returns:
        list[dict]: 会话列表，每项含 session_id, title, last_active_at, message_count
    """
    rows = await _execute_read(
        """
        SELECT
            s.session_id,
            s.last_active_at,
            COALESCE(
                (SELECT SUBSTRING(m.content, 1, 50)
                 FROM messages m
                 WHERE m.session_id = s.session_id AND m.role = 'user'
                 ORDER BY m.created_at ASC
                 LIMIT 1),
                '新对话'
            ) AS title,
            (SELECT COUNT(*) FROM messages m WHERE m.session_id = s.session_id) AS message_count
        FROM sessions s
        WHERE s.user_id = :uid AND s.status = 'active'
        ORDER BY s.last_active_at DESC
        LIMIT :lim
        """,
        {"uid": str(user_id), "lim": limit},
    )
    return rows


async def get_session_messages(session_id: str, limit: int = MAX_MESSAGES) -> list[dict]:
    """获取会话的消息历史

    Args:
        session_id: 会话 ID
        limit: 返回数量上限

    Returns:
        list[dict]: 消息列表，每项含 role, content, created_at
    """
    rows = await _execute_read(
        """
        SELECT role, content, created_at
        FROM messages
        WHERE session_id = :sid
        ORDER BY created_at ASC
        LIMIT :lim
        """,
        {"sid": session_id, "lim": limit},
    )
    return rows


async def delete_session(session_id: str, user_id: int) -> bool:
    """软删除会话（标记为 archived）

    Args:
        session_id: 会话 ID
        user_id: 用户 ID（校验归属）

    Returns:
        bool: 是否成功删除
    """
    affected = await _execute_write(
        """
        UPDATE sessions SET status = 'archived'
        WHERE session_id = :sid AND user_id = :uid
        """,
        {"sid": session_id, "uid": str(user_id)},
    )
    return affected > 0
