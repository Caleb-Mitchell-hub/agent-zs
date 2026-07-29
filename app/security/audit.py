"""审计日志

职责：
- 记录所有 Agent 行为
- 确保不可变（只允许 INSERT）
- 支持全链路追踪
"""

import logging
import json
from datetime import datetime
from typing import Optional

from sqlalchemy import text

from app.db.session import get_session
from app.security.tracing import get_trace_id

logger = logging.getLogger(__name__)


class AuditLogger:
    """审计日志记录器"""

    async def log(
        self,
        action: str,
        user_id: str,
        tenant_id: str,
        request_snapshot: dict = None,
        result_snapshot: dict = None,
        risk_level: str = "low",
        trace_id: str = None,
    ):
        """记录审计日志

        Args:
            action: 操作类型（如 erp_create_expense）
            user_id: 用户ID
            tenant_id: 租户ID
            request_snapshot: 请求快照（执行前）
            result_snapshot: 结果快照（执行后）
            risk_level: 风险级别
            trace_id: 追踪ID
        """
        try:
            # 使用传入的 trace_id 或当前上下文的
            trace_id = trace_id or get_trace_id()

            async for session in get_session():
                await session.execute(
                    text("""
                        INSERT INTO audit_logs (
                            trace_id, user_id, tenant_id, action,
                            request_snapshot, result_snapshot,
                            risk_level, created_at
                        ) VALUES (
                            :trace_id, :user_id, :tenant_id, :action,
                            :request_snapshot, :result_snapshot,
                            :risk_level, :created_at
                        )
                    """),
                    {
                        "trace_id": trace_id,
                        "user_id": user_id,
                        "tenant_id": tenant_id,
                        "action": action,
                        "request_snapshot": json.dumps(request_snapshot, ensure_ascii=False) if request_snapshot else None,
                        "result_snapshot": json.dumps(result_snapshot, ensure_ascii=False) if result_snapshot else None,
                        "risk_level": risk_level,
                        "created_at": datetime.utcnow(),
                    },
                )
                await session.commit()

                logger.info(f"审计日志: {action}, trace={trace_id}")

        except Exception as e:
            logger.error(f"记录审计日志失败: {e}")

    async def get_audit_logs(
        self,
        trace_id: str = None,
        user_id: str = None,
        action: str = None,
        limit: int = 100,
    ) -> list[dict]:
        """查询审计日志"""
        try:
            async for session in get_session():
                conditions = []
                params = {}

                if trace_id:
                    conditions.append("trace_id = :trace_id")
                    params["trace_id"] = trace_id
                if user_id:
                    conditions.append("user_id = :user_id")
                    params["user_id"] = user_id
                if action:
                    conditions.append("action = :action")
                    params["action"] = action

                where_clause = " AND ".join(conditions) if conditions else "1=1"

                result = await session.execute(
                    text(f"SELECT * FROM audit_logs WHERE {where_clause} ORDER BY created_at DESC LIMIT :limit"),
                    {**params, "limit": limit},
                )

                rows = result.mappings().all()
                return [dict(row) for row in rows]

        except Exception as e:
            logger.error(f"查询审计日志失败: {e}")
            return []


# 全局实例
audit_logger = AuditLogger()
