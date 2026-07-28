"""Database Tool - NL→SQL 查询工具

职责：
- 将自然语言转换为 SQL
- 执行 SQL 查询
- 返回结构化结果
"""

import logging
import re
from decimal import Decimal
from typing import Optional

from sqlalchemy import text

from app.db.session import get_session
from app.db.schema import get_summary_ddl
from app.agent.llm_client import llm_client

logger = logging.getLogger(__name__)


# NL-to-SQL Prompt
NL_TO_SQL_PROMPT = """你是一个 SQL 专家。根据用户的自然语言问题，结合数据库 schema，生成正确的 MySQL SQL 语句。

## 数据库 Schema

{schema}

## 对话历史

{history}

## 用户问题

{question}

## 要求

1. 只返回 SQL 语句，不要解释
2. 使用 MySQL 语法
3. 确保 SQL 语句可以直接执行
4. 如果需要多表关联，使用正确的 JOIN 条件
5. 如果涉及日期计算，使用 MySQL 的日期函数
6. 如果问题不明确，返回: CLARIFY: <需要澄清的问题>

## SQL"""


class DatabaseTool:
    """数据库查询工具"""

    def __init__(self):
        self._schema_cache: Optional[str] = None

    async def execute(
        self,
        query: str,
        messages: list[dict],
        context: dict,
    ) -> dict:
        """执行自然语言查询

        Args:
            query: 用户查询
            messages: 历史消息
            context: 会话上下文

        Returns:
            dict: 查询结果
        """
        try:
            # 1. 获取 schema
            schema = await self._get_schema()

            # 2. 构建对话历史
            history = self._build_history(messages)

            # 3. LLM 生成 SQL
            prompt = NL_TO_SQL_PROMPT.format(
                schema=schema,
                history=history,
                question=query,
            )
            llm_response = await llm_client.chat(prompt)

            # 4. 提取 SQL
            sql = self._extract_sql(llm_response)

            # 5. 检查是否需要澄清
            if sql.startswith("CLARIFY:"):
                return {
                    "status": "clarify",
                    "message": sql[8:].strip(),
                    "error_code": "AMBIGUOUS_INPUT",
                }

            logger.info(f"生成 SQL: {sql}")

            # 6. 执行 SQL
            result = await self._execute_sql(sql)

            # 7. 生成摘要
            summary = await self._generate_summary(query, result[:10])

            return {
                "status": "ok",
                "data": result,
                "sql": sql,
                "message": summary,
            }

        except ValueError as e:
            logger.warning(f"SQL 验证失败: {e}")
            return {
                "status": "error",
                "data": None,
                "sql": None,
                "message": str(e),
                "error_code": "INVALID_SQL",
            }

        except Exception as e:
            logger.error(f"查询执行失败: {e}", exc_info=True)
            return {
                "status": "error",
                "data": None,
                "sql": None,
                "message": f"查询执行失败: {str(e)}",
                "error_code": "QUERY_ERROR",
            }

    async def _get_schema(self) -> str:
        """获取数据库 schema（带缓存）"""
        if self._schema_cache is None:
            self._schema_cache = await get_summary_ddl()
        return self._schema_cache

    def _build_history(self, messages: list[dict]) -> str:
        """构建对话历史字符串"""
        if not messages:
            return "无历史对话"

        history_lines = []
        for msg in messages[-5:]:  # 只保留最近 5 条
            role = msg["role"]
            content = msg["content"][:200]  # 截断过长内容
            history_lines.append(f"{role}: {content}")

        return "\n".join(history_lines)

    def _extract_sql(self, llm_response: str) -> str:
        """从 LLM 响应中提取 SQL"""
        # 去掉 markdown 代码块标记
        match = re.search(r'```(?:sql)?\s*(.*?)```', llm_response, re.DOTALL)
        if match:
            return match.group(1).strip()
        return llm_response.strip()

    async def _execute_sql(self, sql: str) -> list[dict]:
        """执行 SQL 查询"""
        # 安全检查
        self._validate_sql(sql)

        async for session in get_session():
            # 设置语句超时
            await session.execute(text("SET SESSION MAX_EXECUTION_TIME = 10000"))

            # 执行查询
            result = await session.execute(text(sql))
            rows = result.mappings().all()

            # 转为字典列表，处理 Decimal 类型
            return [self._convert_decimal(dict(row)) for row in rows[:1000]]

    def _convert_decimal(self, row: dict) -> dict:
        """将 Decimal 类型转换为 float"""
        for key, value in row.items():
            if isinstance(value, Decimal):
                row[key] = float(value)
        return row

    def _validate_sql(self, sql: str):
        """SQL 安全验证"""
        sql_upper = sql.strip().upper()

        # 只允许 SELECT
        if not sql_upper.startswith('SELECT'):
            raise ValueError("只允许 SELECT 查询")

        # 禁止危险关键字
        forbidden = ['INSERT', 'UPDATE', 'DELETE', 'DROP', 'ALTER', 'CREATE', 'TRUNCATE']
        for keyword in forbidden:
            if re.search(rf'\b{keyword}\b', sql_upper):
                raise ValueError(f"禁止使用 {keyword} 语句")

    async def _generate_summary(self, question: str, rows: list[dict]) -> str:
        """生成结果摘要"""
        if not rows:
            return "查询结果为空"

        try:
            from app.agent.prompts import EXPLAIN_PROMPT
            prompt = EXPLAIN_PROMPT.format(
                question=question,
                result=str(rows),
            )
            return await llm_client.chat(prompt)
        except Exception:
            return f"查询返回 {len(rows)} 条数据"
