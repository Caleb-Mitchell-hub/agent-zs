"""Report Agent - 报表 Agent

职责：
- 自然语言转报表
- 图表类型推荐
- 报表渲染
"""

import logging
from typing import Optional

from app.tools.database_tool import DatabaseTool
from app.agent.llm_client import llm_client

logger = logging.getLogger(__name__)


# 报表生成 Prompt
REPORT_PROMPT = """你是一个报表专家。根据用户的自然语言描述，生成报表配置。

## 用户描述
{question}

## 数据库 Schema
{schema}

## 输出格式
返回 JSON 格式：
{{
    "title": "报表标题",
    "sql": "查询SQL",
    "columns": [
        {{"name": "字段名", "label": "列名", "type": "string/number/date"}}
    ],
    "chart_type": "table/bar/line/pie"
}}

## JSON"""


class ReportAgent:
    """报表 Agent"""

    def __init__(self):
        self.db_tool = DatabaseTool()

    async def execute(
        self,
        user_input: str,
        messages: list[dict],
        context: dict,
        session_id: str,
        user_id: int,
        tenant_id: int,
    ) -> dict:
        """执行报表生成任务

        Args:
            user_input: 用户输入
            messages: 历史消息
            context: 会话上下文
            session_id: 会话 ID
            user_id: 用户 ID
            tenant_id: 租户 ID

        Returns:
            dict: 执行结果
        """
        try:
            # 1. 获取 schema
            schema = await self.db_tool._get_schema()

            # 2. LLM 生成报表定义
            prompt = REPORT_PROMPT.format(
                question=user_input,
                schema=schema,
            )
            response = await llm_client.chat(prompt)

            # 3. 解析报表定义
            import re
            import json
            match = re.search(r'```(?:json)?\s*(.*?)```', response, re.DOTALL)
            if match:
                report_def = json.loads(match.group(1).strip())
            else:
                report_def = json.loads(response.strip())

            # 4. 执行查询
            sql = report_def.get("sql")
            if sql:
                result = await self.db_tool._execute_sql(sql)
            else:
                result = []

            return {
                "status": "ok",
                "title": report_def.get("title", "报表"),
                "columns": report_def.get("columns", []),
                "data": result,
                "chart_type": report_def.get("chart_type", "table"),
                "sql": sql,
            }

        except Exception as e:
            logger.error(f"Report Agent 执行失败: {e}", exc_info=True)
            return {
                "status": "error",
                "message": f"报表生成失败: {str(e)}",
            }


# 全局实例
report_agent = ReportAgent()
