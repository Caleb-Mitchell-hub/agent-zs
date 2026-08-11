"""Agent-Zs FastAPI 入口

启动命令: uvicorn app.main:app --host 0.0.0.0 --port 8000
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import settings
from app.logging_config import setup_logging
from app.middleware import RequestLoggingMiddleware, ExceptionHandlerMiddleware
from app.routers import health, query, report, write, rag, admin, workflow, frontend, admin_config, auth, sessions
from app.tools.registry import ToolExecutor

# 配置日志
setup_logging(debug=settings.debug)
logger = logging.getLogger(__name__)

# 工具执行器：统一强制执行超时/重试/二次确认（后续接线使用）
tool_executor = ToolExecutor()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    logger.info(f"启动 {settings.app_name} v{settings.app_version}")

    # 初始化数据库
    from app.db.session import init_db
    await init_db()
    logger.info("数据库连接池初始化完成")

    # 初始化 Redis
    from app.memory.session_memory import init_redis
    await init_redis()
    logger.info("Redis 连接初始化完成")

    # 注册工具
    from app.tools.registry import tool_registry
    from app.tools.database_tool import DatabaseTool
    from app.tools.search_tool import SearchTool
    from app.tools.time_tool import TimeTool
    from app.tools.report_templates import report_template_engine

    db_tool = DatabaseTool()
    search_tool = SearchTool()
    time_tool = TimeTool()

    tool_registry.register("query_tool", db_tool.execute, "查询数据库", permission_level="medium", risk_level="medium")
    tool_registry.register("knowledge_tool", search_tool.execute, "知识检索", permission_level="low", risk_level="low")
    tool_registry.register("time_tool", time_tool.execute, "实时时间查询", permission_level="low", risk_level="low")
    logger.info(f"工具注册完成: {len(tool_registry.list_tools())} 个工具")

    # 应用工具策略（从配置中心加载）
    from app.config_center.service import config_service
    await config_service.apply_tool_policies(tool_registry)

    # 加载限流配置
    from app.gateway.rate_limit import rate_limiter
    await rate_limiter.load_from_config()

    # 启动 Task Worker
    from app.worker.task_worker import task_worker
    await task_worker.start()
    logger.info("Task Worker 启动完成")

    yield

    # 停止 Task Worker
    from app.worker.task_worker import task_worker
    await task_worker.stop()

    # 清理
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
app.include_router(frontend.router, tags=["前端"])
app.include_router(health.router, tags=["健康检查"])
app.include_router(query.router, prefix="/api/v1", tags=["查询"])
app.include_router(report.router, prefix="/api/v1", tags=["报表"])
app.include_router(write.router, prefix="/api/v1", tags=["单据"])
app.include_router(rag.router, prefix="/api/v1", tags=["知识检索"])
app.include_router(admin.router, prefix="/api/v1", tags=["管理"])
app.include_router(admin_config.router, prefix="/api/v1", tags=["配置中心"])
app.include_router(auth.router, prefix="/api/v1", tags=["认证"])
app.include_router(sessions.router, prefix="/api/v1", tags=["会话"])
app.include_router(workflow.router, prefix="/api/v1", tags=["工作流"])
