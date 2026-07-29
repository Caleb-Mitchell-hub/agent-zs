"""Database Tool - NL→SQL 查询工具

职责：
- 将自然语言转换为 SQL
- 执行 SQL 查询
- 返回结构化结果（中文字段名，只返回业务字段）
"""

import json
import logging
import re
from decimal import Decimal

from sqlalchemy import text

from app.db.session import get_session
from app.db.schema import get_summary_ddl
from app.agent.llm_client import llm_client

logger = logging.getLogger(__name__)


# 字段名映射表（数据库字段名 → 中文显示名）
FIELD_NAME_MAP = {
    # 采购订单
    "order_no": "订单编号",
    "supplier_name": "供应商",
    "warehouse_name": "仓库",
    "order_date": "订单日期",
    "total_amount": "订单金额",
    "pay_amount": "应付金额",
    "status": "状态",
    "delivery_date": "预计到货日期",
    "payment_method": "付款方式",
    "contact_name": "联系人",
    "contact_phone": "联系电话",
    "remark": "备注",
    "created_at": "创建时间",
    "updated_at": "更新时间",
    # 销售订单
    "customer_name": "客户",
    "received_amount": "已收款金额",
    # 报销单
    "reimbursement_no": "报销单号",
    "expense_type": "报销类型",
    "amount": "金额",
    "actual_amount": "实际金额",
    "reason": "报销原因",
    "department": "部门",
    # 库存
    "warehouse_id": "仓库ID",
    "sku_id": "SKU ID",
    "quantity": "库存数量",
    "locked_quantity": "锁定数量",
    "available_quantity": "可用数量",
    "avg_cost": "平均成本",
    # 入库单
    "in_no": "入库单号",
    "in_type": "入库类型",
    "total_quantity": "总数量",
    # 出库单
    "out_no": "出库单号",
    "out_type": "出库类型",
}

# 需要排除的系统字段
EXCLUDE_FIELDS = {
    "id", "tenant_id", "company_id", "deleted", "version",
    "created_by", "applicant_id", "approver_id",
    "auto_stock_in", "source_type", "source_no",
    "submitted_at", "approved_at", "approved_at2",
    "payment_account", "submitted_at",
}

# 状态值映射
STATUS_MAP = {
    "DRAFT": "草稿",
    "SUBMITTED": "已提交",
    "APPROVED": "已审批",
    "REJECTED": "已驳回",
    "CANCELLED": "已取消",
    "CONFIRMED": "已确认",
    "COMPLETED": "已完成",
    "PENDING": "待处理",
}

NL_TO_SQL_PROMPT = """你是一个 SQL 专家。根据用户的自然语言问题，结合数据库 schema，生成正确的 MySQL SQL 语句。

## 数据库 Schema
{schema}

## 用户问题
{question}

## 要求
1. 只返回 SQL 语句，不要解释
2. 使用 MySQL 语法
3. 只查询业务相关字段，不要查询 id, tenant_id, deleted 等系统字段
4. 如果需要多表关联，使用正确的 JOIN 条件
5. 如果问题不明确，返回: CLARIFY: <需要澄清的问题>
6. 对于名称字段（如仓库名称 warehouse_name、供应商名称 supplier_name、客户名称 customer_name），使用 LIKE '%关键词%' 进行模糊匹配
7. 例如用户说"北京市"，应该用 warehouse_name LIKE '%北京%' 而不是 region_path LIKE '%北京市%'

## SQL"""


class DatabaseTool:
    """数据库查询工具"""

    def __init__(self):
        self._schema_cache = None

    async def execute(self, query: str, messages: list[dict], context: dict) -> dict:
        """执行自然语言查询"""
        try:
            # 1. 获取 schema
            schema = await self._get_schema()

            # 2. 构建对话历史
            history = self._build_history(messages)

            # 3. LLM 生成 SQL
            prompt = NL_TO_SQL_PROMPT.format(schema=schema, history=history, question=query)
            llm_response = await llm_client.chat(prompt)

            # 4. 提取 SQL
            sql = self._extract_sql(llm_response)

            # 5. 检查是否需要澄清
            if sql.startswith("CLARIFY:"):
                return {"status": "clarify", "message": sql[8:].strip(), "error_code": "AMBIGUOUS_INPUT"}

            # 6. 执行 SQL
            result = await self._execute_sql(sql)

            # 7. 转换字段名为中文
            result = self._translate_fields(result)

            # 8. 生成摘要
            summary = await self._generate_summary(query, result[:10])

            return {"status": "ok", "data": result, "sql": sql, "message": summary}

        except ValueError as e:
            return {"status": "error", "data": None, "sql": None, "message": str(e), "error_code": "INVALID_SQL"}
        except Exception as e:
            logger.error(f"查询执行失败: {e}", exc_info=True)
            return {"status": "error", "data": None, "sql": None, "message": f"查询失败: {str(e)}", "error_code": "QUERY_ERROR"}

    async def _get_schema(self) -> str:
        if self._schema_cache is None:
            self._schema_cache = await get_summary_ddl()
        return self._schema_cache

    def _build_history(self, messages: list[dict]) -> str:
        if not messages:
            return "无历史对话"
        history_lines = []
        for msg in messages[-5:]:
            history_lines.append(f"{msg['role']}: {msg['content'][:200]}")
        return "\n".join(history_lines)

    def _extract_sql(self, llm_response: str) -> str:
        match = re.search(r'```(?:sql)?\s*(.*?)```', llm_response, re.DOTALL)
        if match:
            return match.group(1).strip()
        return llm_response.strip()

    async def _execute_sql(self, sql: str) -> list[dict]:
        self._validate_sql(sql)
        async for session in get_session():
            await session.execute(text("SET SESSION MAX_EXECUTION_TIME = 10000"))
            result = await session.execute(text(sql))
            rows = result.mappings().all()
            return [self._convert_decimal(dict(row)) for row in rows[:1000]]

    def _validate_sql(self, sql: str):
        sql_upper = sql.strip().upper()
        if not sql_upper.startswith('SELECT'):
            raise ValueError("只允许 SELECT 查询")
        forbidden = ['INSERT', 'UPDATE', 'DELETE', 'DROP', 'ALTER', 'CREATE', 'TRUNCATE']
        for keyword in forbidden:
            if re.search(rf'\b{keyword}\b', sql_upper):
                raise ValueError(f"禁止使用 {keyword} 语句")

    def _convert_decimal(self, row: dict) -> dict:
        for key, value in row.items():
            if isinstance(value, Decimal):
                row[key] = float(value)
        return row

    def _translate_fields(self, data: list[dict]) -> list[dict]:
        """转换字段名为中文，排除系统字段"""
        if not data:
            return data

        translated = []
        for row in data:
            new_row = {}
            for key, value in row.items():
                # 排除系统字段
                if key in EXCLUDE_FIELDS:
                    continue
                # 排除 custom_ 开头的自定义字段
                if key.startswith("custom_"):
                    continue
                # 排除 creator_ 开头的创建人字段
                if key.startswith("creator_"):
                    continue

                # 转换字段名
                display_name = FIELD_NAME_MAP.get(key, key)

                # 转换状态值
                if key == "status" and value in STATUS_MAP:
                    value = STATUS_MAP[value]

                new_row[display_name] = value
            translated.append(new_row)

        return translated

    async def _generate_summary(self, question: str, rows: list[dict]) -> str:
        if not rows:
            return "查询结果为空"
        try:
            from app.agent.prompts import EXPLAIN_PROMPT
            prompt = EXPLAIN_PROMPT.format(question=question, result=str(rows))
            return await llm_client.chat(prompt)
        except Exception:
            return f"查询返回 {len(rows)} 条数据"
