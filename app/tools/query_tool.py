"""查询工具 - SQL 沙箱执行

执行 LLM 生成的 SQL 查询，包含安全限制：
- 只允许 SELECT 语句
- statement_timeout 超时控制
- 最大返回行数限制
"""

import re

from sqlalchemy import text

from app.config import settings
from app.db.session import get_session


class QueryResult:
    """查询结果"""

    def __init__(self, rows: list[dict], sql: str, row_count: int):
        self.rows = rows
        self.sql = sql
        self.row_count = row_count

    def to_dict(self) -> dict:
        return {
            "rows": self.rows,
            "sql": self.sql,
            "row_count": self.row_count,
        }


async def execute_sql_sandbox(sql: str) -> QueryResult:
    """在沙箱中执行 SQL 查询

    安全限制：
    1. 只允许 SELECT 语句
    2. 禁止 DDL（CREATE/ALTER/DROP）
    3. 禁止 DML（INSERT/UPDATE/DELETE）
    4. 超时控制（statement_timeout）
    5. 最大返回行数限制
    """
    # 安全检查
    _validate_sql(sql)

    async for session in get_session():
        # 设置语句超时
        await session.execute(
            text(f"SET SESSION MAX_EXECUTION_TIME = {settings.sql_statement_timeout * 1000}")
        )

        # 执行查询
        result = await session.execute(text(sql))
        rows = result.mappings().all()

        # 转为字典列表
        data = [dict(row) for row in rows[:settings.sql_max_rows]]

        return QueryResult(
            rows=data,
            sql=sql,
            row_count=len(data),
        )


def _validate_sql(sql: str):
    """SQL 安全验证"""
    sql_upper = sql.strip().upper()

    # 只允许 SELECT
    if not sql_upper.startswith('SELECT'):
        raise ValueError("只允许 SELECT 查询")

    # 禁止危险关键字
    forbidden = ['INSERT', 'UPDATE', 'DELETE', 'DROP', 'ALTER', 'CREATE', 'TRUNCATE', 'GRANT', 'REVOKE']
    for keyword in forbidden:
        # 检查是否作为独立关键字出现（非字符串中的子串）
        if re.search(rf'\b{keyword}\b', sql_upper):
            raise ValueError(f"禁止使用 {keyword} 语句")
