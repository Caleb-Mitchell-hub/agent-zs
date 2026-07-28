"""报表工具 - 基于查询结果生成结构化报表

流程：
1. LLM 生成 SQL + 报表标题 + 列定义
2. 执行 SQL 获取数据
3. 格式化为报表结构
"""

import re
import json

from app.agent.llm_client import llm_client
from app.agent.prompts import REPORT_PROMPT
from app.tools.query_tool import execute_sql_sandbox


class ReportResult:
    """报表结果"""

    def __init__(self, title: str, columns: list[dict], rows: list[dict], sql: str):
        self.title = title
        self.columns = columns  # [{"name": "...", "label": "...", "type": "..."}]
        self.rows = rows
        self.sql = sql

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "columns": self.columns,
            "rows": self.rows,
            "sql": self.sql,
        }


async def generate_report(question: str, schema: str) -> ReportResult:
    """根据自然语言描述生成报表

    流程：
    1. LLM 生成 SQL + 报表标题 + 列定义
    2. 执行 SQL 获取数据
    3. 格式化为报表结构
    """
    # 1. LLM 生成报表定义
    prompt = REPORT_PROMPT.format(schema=schema, question=question)
    llm_response = await llm_client.chat(prompt)

    # 2. 解析 LLM 响应
    report_def = _parse_report_definition(llm_response)

    # 3. 执行 SQL
    result = await execute_sql_sandbox(report_def['sql'])

    # 4. 构建报表
    return ReportResult(
        title=report_def['title'],
        columns=report_def['columns'],
        rows=result.rows,
        sql=result.sql,
    )


def _parse_report_definition(llm_response: str) -> dict:
    """解析 LLM 返回的报表定义 JSON"""
    # 提取 JSON
    match = re.search(r'```(?:json)?\s*(.*?)```', llm_response, re.DOTALL)
    if match:
        json_str = match.group(1).strip()
    else:
        json_str = llm_response.strip()

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError:
        # 尝试修复常见问题
        # 有时候 LLM 会在 JSON 前后添加说明文字
        json_match = re.search(r'\{.*\}', json_str, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group())
        else:
            raise ValueError(f"无法解析报表定义: {llm_response[:200]}")

    # 验证必要字段
    required_fields = ['title', 'sql', 'columns']
    for field in required_fields:
        if field not in data:
            raise ValueError(f"报表定义缺少必要字段: {field}")

    return data
