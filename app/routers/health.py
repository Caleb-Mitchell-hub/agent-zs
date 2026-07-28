"""健康检查端点"""

import time
from fastapi import APIRouter

from app.config import settings
from app.db.session import get_session

router = APIRouter()


@router.get("/health")
async def health_check():
    """健康检查

    返回服务状态、版本、数据库连接状态。
    """
    db_status = "unknown"
    db_latency_ms = None

    # 检查数据库连接
    try:
        start = time.time()
        async for session in get_session():
            from sqlalchemy import text
            await session.execute(text("SELECT 1"))
        db_latency_ms = round((time.time() - start) * 1000, 1)
        db_status = "ok"
    except Exception as e:
        db_status = f"error: {str(e)}"

    return {
        "status": "ok" if db_status == "ok" else "degraded",
        "service": settings.app_name,
        "version": settings.app_version,
        "database": {
            "status": db_status,
            "latency_ms": db_latency_ms,
        },
    }
