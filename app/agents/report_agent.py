"""Report Agent - 报表 Agent

职责：
- 自然语言转报表
- 图表类型推荐
- 报表渲染
"""

import logging
import re
from datetime import date, timedelta
from typing import Optional

from app.tools.database_tool import DatabaseTool
from app.agent.llm_client import llm_client
from app.tools.report_templates import report_template_engine

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


def _parse_date_range(user_input: str) -> tuple[str, str]:
    """从用户输入解析时间范围，返回 (start_date, end_date)，格式 YYYY-MM-DD

    支持：近N天/近N日、本月、上月、今年、去年；解析不到则默认最近30天。
    """
    today = date.today()

    # 近N天 / 近N日
    m = re.search(r'近\s*(\d{1,3})\s*[天日]', user_input)
    if m:
        days = int(m.group(1))
        start = today - timedelta(days=days)
        end = today + timedelta(days=1)
        return start.isoformat(), end.isoformat()

    # 本月
    if re.search(r'本月|这个月', user_input):
        if today.month == 12:
            end = date(today.year + 1, 1, 1)
        else:
            end = date(today.year, today.month + 1, 1)
        return date(today.year, today.month, 1).isoformat(), end.isoformat()

    # 上月
    if re.search(r'上月|上个月', user_input):
        if today.month == 1:
            start = date(today.year - 1, 12, 1)
            end = date(today.year, 1, 1)
        else:
            start = date(today.year, today.month - 1, 1)
            end = date(today.year, today.month, 1)
        return start.isoformat(), end.isoformat()

    # 今年
    if re.search(r'今年', user_input):
        return date(today.year, 1, 1).isoformat(), date(today.year + 1, 1, 1).isoformat()

    # 去年
    if re.search(r'去年', user_input):
        return date(today.year - 1, 1, 1).isoformat(), date(today.year, 1, 1).isoformat()

    # 默认最近30天
    start = today - timedelta(days=30)
    end = today + timedelta(days=1)
    return start.isoformat(), end.isoformat()


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
            # 1. 优先匹配预置模板（命中则零 LLM 调用）
            template = report_template_engine.match_template(user_input)
            if template:
                return await self._generate_from_template(template, user_input)

            # 2. 未命中，获取 schema
            schema = await self.db_tool._get_schema()

            # 3. LLM 生成报表定义
            prompt = REPORT_PROMPT.format(
                question=user_input,
                schema=schema,
            )
            response = await llm_client.chat(prompt)

            # 4. 解析报表定义
            import json
            match = re.search(r'```(?:json)?\s*(.*?)```', response, re.DOTALL)
            if match:
                report_def = json.loads(match.group(1).strip())
            else:
                report_def = json.loads(response.strip())

            # 5. 执行查询
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

    async def _generate_from_template(self, template: dict, user_input: str) -> dict:
        """使用预置模板生成报表（零 LLM 调用）

        Args:
            template: 匹配到的报表模板
            user_input: 用户输入

        Returns:
            dict: 执行结果
        """
        # 模板 SQL 需要日期参数时，从用户输入解析时间范围（解析不到默认最近30天）
        params = {}
        if "{start_date}" in template["sql_template"]:
            start_date, end_date = _parse_date_range(user_input)
            params["start_date"] = start_date
            params["end_date"] = end_date

        # 参数化生成 SQL（generate_sql 内部对日期做安全校验）
        sql = report_template_engine.generate_sql(template, params)

        # 执行查询
        result = await self.db_tool._execute_sql(sql)

        return {
            "status": "ok",
            "title": template["name"],
            "columns": template["columns"],
            "data": result,
            "chart_type": template["chart_type"],
            "sql": sql,
        }


# 全局实例
report_agent = ReportAgent()
