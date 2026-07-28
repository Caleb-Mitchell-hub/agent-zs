"""Schema 工具 - 获取数据库表结构摘要

用于 NL-to-SQL 场景，提供给 LLM 的 schema 摘要 DDL。
"""

from sqlalchemy import text
from app.db.session import get_session


async def get_table_list() -> list[str]:
    """获取所有表名"""
    async for session in get_session():
        result = await session.execute(text("SHOW TABLES"))
        return [row[0] for row in result.fetchall()]


async def get_create_table(table_name: str) -> str:
    """获取单张表的 CREATE TABLE 语句"""
    async for session in get_session():
        result = await session.execute(
            text(f"SHOW CREATE TABLE `{table_name}`")
        )
        row = result.fetchone()
        return row[1] if row else ""


async def get_summary_ddl() -> str:
    """获取所有业务表的精简 schema 摘要

    过滤掉系统表（ACT_/act_/FLW_/flw_），
    只保留核心列定义（去掉 custom_* 扩展字段）。
    """
    tables = await get_table_list()

    # 过滤系统表
    biz_tables = [
        t for t in tables
        if not t.startswith(('ACT_', 'act_', 'FLW_', 'flw_'))
    ]

    summaries = []
    for table in biz_tables:
        ddl = await get_create_table(table)
        if not ddl:
            continue

        # 精简：只保留核心列
        lines = ddl.split('\n')
        core_lines = [f"CREATE TABLE `{table}` ("]
        for line in lines:
            stripped = line.strip()
            # 跳过 custom_* 字段、索引定义、表选项
            if stripped.startswith('`custom_'):
                continue
            if stripped.startswith(('PRIMARY KEY', 'KEY ', 'UNIQUE KEY', 'CONSTRAINT')):
                continue
            if stripped.startswith((') ENGINE=', 'COMMENT=')):
                continue
            if stripped.startswith('`'):
                core_lines.append(f"  {stripped}")

        # 移除最后一个逗号
        if core_lines[-1].rstrip().endswith(','):
            core_lines[-1] = core_lines[-1].rstrip()[:-1]

        core_lines.append(");")
        summaries.append('\n'.join(core_lines))

    return '\n\n'.join(summaries)
