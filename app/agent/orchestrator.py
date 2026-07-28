"""Agent 编排引擎

负责 NL→SQL→执行→结果 的完整链路。
"""

import re
import logging
from typing import AsyncGenerator

from app.agent.llm_client import llm_client
from app.agent.prompts import NL_TO_SQL_PROMPT, EXPLAIN_PROMPT
from app.tools.schema_tool import get_schema_for_llm
from app.tools.query_tool import execute_sql_sandbox
from app.tools.report_tool import generate_report

logger = logging.getLogger(__name__)


class QueryOrchestrator:
    """查询编排器"""

    async def process_query(self, question: str, tenant_id: int = None) -> dict:
        """处理自然语言查询

        流程：
        1. 获取 schema 摘要
        2. LLM 生成 SQL
        3. 安全验证
        4. 沙箱执行
        5. 返回结果
        """
        try:
            # 1. 获取 schema
            schema = await get_schema_for_llm()
            logger.info(f"获取 schema 完成，长度: {len(schema)}")

            # 2. LLM 生成 SQL
            prompt = NL_TO_SQL_PROMPT.format(schema=schema, question=question)
            llm_response = await llm_client.chat(prompt)
            logger.info(f"LLM 响应: {llm_response[:200]}...")

            # 3. 提取 SQL
            sql = self._extract_sql(llm_response)

            # 检查是否需要澄清
            if sql.startswith("CLARIFY:"):
                return {
                    "status": "clarify",
                    "data": None,
                    "sql": None,
                    "message": sql[8:].strip(),
                    "error_code": "AMBIGUOUS_INPUT",
                }

            logger.info(f"生成 SQL: {sql}")

            # 4. 执行查询
            result = await execute_sql_sandbox(sql)
            logger.info(f"查询返回 {result.row_count} 行")

            # 5. 生成结果摘要
            summary = await self._generate_summary(question, result.rows[:10])

            return {
                "status": "ok",
                "data": result.rows,
                "sql": result.sql,
                "message": summary,
                "error_code": None,
            }

        except ValueError as e:
            # SQL 安全验证失败
            logger.warning(f"SQL 验证失败: {e}")
            return {
                "status": "error",
                "data": None,
                "sql": None,
                "message": str(e),
                "error_code": "INVALID_SQL",
            }

        except Exception as e:
            logger.error(f"查询处理失败: {e}", exc_info=True)
            return {
                "status": "error",
                "data": None,
                "sql": None,
                "message": f"查询处理失败: {str(e)}",
                "error_code": "LLM_UNAVAILABLE",
            }

    async def process_query_stream(self, question: str, tenant_id: int = None) -> AsyncGenerator[str, None]:
        """SSE 流式查询

        流式输出查询进度和结果。
        """
        import json

        # 发送进度
        yield json.dumps({"type": "progress", "message": "正在分析问题..."}, ensure_ascii=False)

        # 获取 schema
        schema = await get_schema_for_llm()
        yield json.dumps({"type": "progress", "message": "正在生成 SQL..."}, ensure_ascii=False)

        # LLM 生成 SQL
        prompt = NL_TO_SQL_PROMPT.format(schema=schema, question=question)
        llm_response = await llm_client.chat(prompt)
        sql = self._extract_sql(llm_response)

        yield json.dumps({"type": "sql", "sql": sql}, ensure_ascii=False)

        # 检查是否需要澄清
        if sql.startswith("CLARIFY:"):
            yield json.dumps({
                "type": "clarify",
                "message": sql[8:].strip(),
            }, ensure_ascii=False)
            return

        yield json.dumps({"type": "progress", "message": "正在执行查询..."}, ensure_ascii=False)

        # 执行查询
        try:
            result = await execute_sql_sandbox(sql)
            yield json.dumps({
                "type": "result",
                "data": result.rows,
                "row_count": result.row_count,
            }, ensure_ascii=False)
        except Exception as e:
            yield json.dumps({
                "type": "error",
                "message": str(e),
            }, ensure_ascii=False)

    def _extract_sql(self, llm_response: str) -> str:
        """从 LLM 响应中提取纯 SQL"""
        # 去掉 markdown 代码块标记
        match = re.search(r'```(?:sql)?\s*(.*?)```', llm_response, re.DOTALL)
        if match:
            return match.group(1).strip()

        # 如果没有代码块，直接返回（可能是纯 SQL 或 CLARIFY）
        return llm_response.strip()

    async def _generate_summary(self, question: str, rows: list[dict]) -> str:
        """生成结果摘要"""
        if not rows:
            return "查询结果为空"

        try:
            prompt = EXPLAIN_PROMPT.format(
                question=question,
                result=str(rows),
            )
            summary = await llm_client.chat(prompt)
            return summary
        except Exception:
            # 摘要生成失败不影响主流程
            return f"查询返回 {len(rows)} 条数据"


class ReportOrchestrator:
    """报表编排器"""

    async def process_report(self, question: str, format: str = "table") -> dict:
        """处理报表请求

        流程：
        1. 获取 schema 摘要
        2. 调用 report_tool 生成报表
        3. 返回结构化报表数据
        """
        try:
            # 1. 获取 schema
            schema = await get_schema_for_llm()

            # 2. 生成报表
            report = await generate_report(question, schema)

            return {
                "status": "ok",
                "data": report.rows,
                "title": report.title,
                "columns": report.columns,
                "message": None,
                "error_code": None,
            }

        except ValueError as e:
            logger.warning(f"报表生成失败: {e}")
            return {
                "status": "error",
                "data": None,
                "title": None,
                "columns": None,
                "message": str(e),
                "error_code": "INVALID_REPORT",
            }

        except Exception as e:
            logger.error(f"报表处理失败: {e}", exc_info=True)
            return {
                "status": "error",
                "data": None,
                "title": None,
                "columns": None,
                "message": f"报表处理失败: {str(e)}",
                "error_code": "LLM_UNAVAILABLE",
            }
