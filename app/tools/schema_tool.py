"""Schema 工具 - 提供数据库表结构给 LLM"""

from app.db.schema import get_summary_ddl


async def get_schema_for_llm() -> str:
    """获取精简的 schema 摘要，用于 LLM 的 NL-to-SQL 转换

    返回格式：CREATE TABLE 语句（只包含核心字段，去掉 custom_* 扩展字段）
    """
    return await get_summary_ddl()
