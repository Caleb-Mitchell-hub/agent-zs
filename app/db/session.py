"""数据库会话管理

使用 SQLAlchemy 2.0 异步引擎 + 连接池。
"""

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import text

from app.config import settings

# 异步引擎（延迟初始化）
engine = None
async_session_factory = None


async def init_db():
    """初始化数据库连接池"""
    global engine, async_session_factory

    engine = create_async_engine(
        settings.database_url,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_recycle=settings.db_pool_recycle,
        echo=settings.debug,
    )

    async_session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


async def close_db():
    """关闭数据库连接池"""
    global engine
    if engine:
        await engine.dispose()


async def get_session() -> AsyncSession:
    """获取数据库会话（用于依赖注入）"""
    if async_session_factory is None:
        raise RuntimeError("数据库未初始化，请先调用 init_db()")
    async with async_session_factory() as session:
        yield session


async def execute_query(sql: str, params: dict = None) -> list[dict]:
    """执行只读查询，返回字典列表

    用于 query_tool 的 SQL 沙箱执行。
    """
    if async_session_factory is None:
        raise RuntimeError("数据库未初始化")

    async with async_session_factory() as session:
        result = await session.execute(text(sql), params or {})
        rows = result.mappings().all()
        return [dict(row) for row in rows]
