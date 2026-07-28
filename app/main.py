"""Agent-Zs FastAPI 入口

启动命令: uvicorn app.main:app --host 0.0.0.0 --port 8000
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import settings
from app.logging_config import setup_logging
from app.middleware import RequestLoggingMiddleware, ExceptionHandlerMiddleware
from app.routers import query, report, health, admin, write, rag

# 配置日志
setup_logging(debug=settings.debug)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时：初始化数据库连接池
    logger.info(f"启动 {settings.app_name} v{settings.app_version}")
    from app.db.session import init_db
    await init_db()
    logger.info("数据库连接池初始化完成")

    yield

    # 关闭时：清理连接池
    from app.db.session import close_db
    await close_db()
    logger.info("数据库连接池已关闭")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="ERP 自然语言操作层 - 用自然语言查询和操作 ERP 数据",
    lifespan=lifespan,
)

# 注册中间件（顺序很重要：先注册的后执行）
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(ExceptionHandlerMiddleware)

# 注册路由
app.include_router(health.router, tags=["健康检查"])
app.include_router(query.router, prefix="/api/v1", tags=["查询"])
app.include_router(report.router, prefix="/api/v1", tags=["报表"])
app.include_router(admin.router, prefix="/api/v1", tags=["管理"])
app.include_router(write.router, prefix="/api/v1", tags=["单据"])
app.include_router(rag.router, prefix="/api/v1", tags=["知识检索"])
