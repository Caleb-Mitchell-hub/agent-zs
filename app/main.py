"""Agent-Zs FastAPI 入口

启动命令: uvicorn app.main:app --host 0.0.0.0 --port 8000
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import settings
from app.logging_config import setup_logging
from app.middleware import RequestLoggingMiddleware, ExceptionHandlerMiddleware
from app.routers import health, query, report, write, rag, admin, workflow

# 配置日志
setup_logging(debug=settings.debug)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时：初始化数据库连接池和 Redis
    logger.info(f"启动 {settings.app_name} v{settings.app_version}")

    from app.db.session import init_db
    await init_db()
    logger.info("数据库连接池初始化完成")

    from app.memory.session_memory import init_redis
    await init_redis()
    logger.info("Redis 连接初始化完成")

    # 启动 Task Worker
    from app.worker.task_worker import task_worker
    await task_worker.start()
    logger.info("Task Worker 启动完成")

    yield

    # 停止 Task Worker
    from app.worker.task_worker import task_worker
    await task_worker.stop()

    # 关闭时：清理连接池
    from app.db.session import close_db
    await close_db()

    from app.memory.session_memory import close_redis
    await close_redis()

    logger.info("连接池已关闭")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="企业级 ERP 自然语言智能操作层",
    lifespan=lifespan,
)

# 注册中间件
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(ExceptionHandlerMiddleware)

# 注册路由
app.include_router(health.router, tags=["健康检查"])
app.include_router(query.router, prefix="/api/v1", tags=["查询"])
app.include_router(report.router, prefix="/api/v1", tags=["报表"])
app.include_router(write.router, prefix="/api/v1", tags=["单据"])
app.include_router(rag.router, prefix="/api/v1", tags=["知识检索"])
app.include_router(admin.router, prefix="/api/v1", tags=["管理"])
app.include_router(workflow.router, prefix="/api/v1", tags=["工作流"])
