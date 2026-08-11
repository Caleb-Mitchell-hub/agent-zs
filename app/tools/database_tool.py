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

from app.config import settings
from app.db.session import get_session
from app.db.schema import get_schema_structure, get_summary_ddl
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
    # 用户
    "username": "用户名",
    "real_name": "真实姓名",
    "phone": "手机号",
    "email": "邮箱",
    "dept_id": "部门ID",
    "last_login_time": "最后登录时间",
    "last_login_ip": "最后登录IP",
    "region_id": "区域ID",
    "gender": "性别",
    "birthday": "生日",
    "position": "职位",
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

# 常见 SQL 关键字/聚合函数，用于列名校验时跳过，避免误报
SQL_RESERVED = {
    "COUNT", "SUM", "AVG", "MIN", "MAX", "DISTINCT", "ALL", "AS", "ASC", "DESC",
    "CASE", "WHEN", "THEN", "ELSE", "END", "NULL", "TRUE", "FALSE",
    "IF", "IFNULL", "NULLIF", "COALESCE", "CONCAT", "CONCAT_WS", "GROUP_CONCAT",
    "ROUND", "FLOOR", "CEIL", "CEILING", "ABS", "MOD", "POWER", "SQRT",
    "NOW", "CURDATE", "CURTIME", "DATE", "YEAR", "MONTH", "DAY", "HOUR",
    "MINUTE", "SECOND", "DATE_FORMAT", "STR_TO_DATE", "DATE_ADD", "DATE_SUB",
    "DATEDIFF", "TIMESTAMPDIFF",
    "JSON_EXTRACT", "JSON_UNQUOTE", "CAST", "CONVERT", "SUBSTRING", "SUBSTR",
    "LEFT", "RIGHT", "LENGTH", "CHAR_LENGTH", "UPPER", "LOWER", "REPLACE",
    "TRIM", "LTRIM", "RTRIM", "LOCATE", "INSTR",
    "GROUP", "ORDER", "BY", "LIMIT", "OFFSET", "UNION", "AND", "OR", "NOT",
    "IN", "IS", "LIKE", "BETWEEN", "EXISTS", "ON", "USING", "HAVING",
}

NL_TO_SQL_PROMPT = """你是一个 SQL 专家。根据用户的自然语言问题，结合数据库 schema 和对话上下文，生成正确的 MySQL SQL 语句。

## 数据库 Schema
{schema}

## 对话历史（最近几轮问答，用于理解代词和省略）
{history}

## 上一轮查询参考（理解"X呢？"等追问的模板：沿用相同查询结构，替换条件值）
{context_hint}

{user_memory}

{permission_block}

## 用户问题（结合上面的对话历史和查询参考理解）
{question}

## 严格要求（必须遵守）
1. 只返回 SQL 语句，不要解释
2. 使用 MySQL 语法
3. **绝对禁止编造 schema 中不存在的列名！** 只能使用 schema 中明确定义的列。不确定的列名一律不要用
4. 只查询业务相关字段，不要查询 id, tenant_id, deleted, created_by, updated_by 等系统字段
5. 如果需要多表关联，使用正确的 JOIN 条件
6. 如果问题不明确，返回: CLARIFY: <需要澄清的问题>
7. **重要：结合对话历史理解省略和代词。** 例如：
   - 历史："查询上海仓库的库存" → 用户问"北京呢？" → 理解为"查询北京仓库的库存"
   - 历史："列出广州的仓库" → 用户问"库存有多少？" → 理解为"查询广州仓库的库存"
   - 历史："查询张三的采购订单" → 用户问"李四呢？" → 理解为"查询李四的采购订单"
8. 地名/区域查询规则：
   - 用户说"北京"、"上海市"等**纯区域名**（不包含"仓库"字样）时，按地址 address 字段模糊匹配
   - 例如：address LIKE '%北京%'
   - **重要：如果用户输入中包含"仓库"二字（如"上海仓库3"），说明用户指定的是仓库名称，不是区域，此时必须走规则9！**
9. 仓库名称匹配规则（**优先级高于区域规则**）：
   - 当用户输入中包含"仓库"+"编号/数字"（如"上海仓库3"、"北京仓1号"、"广州1号仓"、"A仓"），说明用户指定了具体的仓库名称
   - **必须**用 warehouse_name 精确匹配，**禁止**当成区域名去查 address
   - 正确示例：用户"汇总上海仓库3的数量" → WHERE w.warehouse_name LIKE '%上海仓库3%'
   - 正确示例：用户"查询北京仓库1的库存" → WHERE w.warehouse_name LIKE '%北京仓库1%'
   - 错误示例：WHERE w.address LIKE '%上海%'（这样会把上海仓库1、2、3全查出来）
10. 库存查询规则：
   - 查询"某仓库的库存/数量"时，需要 JOIN warehouse 和 inventory 表，并按仓库名过滤
   - 返回每个仓库的每个 SKU 的库存数量
   - 正确示例：SELECT w.warehouse_name, i.sku_id, i.quantity FROM inventory i JOIN warehouse w ON i.warehouse_id = w.id WHERE w.warehouse_name LIKE '%上海仓库3%'
   - 如果是汇总查询（如"汇总数量"），使用 SUM 聚合：SELECT w.warehouse_name, SUM(i.quantity) AS 总数量 FROM inventory i JOIN warehouse w ON i.warehouse_id = w.id WHERE w.warehouse_name LIKE '%上海仓库3%' GROUP BY w.warehouse_name

## SQL"""


class DatabaseTool:
    """数据库查询工具"""

    def __init__(self):
        self._schema_cache = None

    async def execute(self, query: str, messages: list[dict], context: dict,
                      user_permissions: dict | None = None, user_id: int = 0) -> dict:
        """执行自然语言查询，SQL 错误时自动修正重试

        Args:
            query: 用户自然语言问题
            messages: 对话历史
            context: 会话上下文
            user_permissions: 用户数据权限范围（warehouse_ids/region_ids/customer_ids/product_ids）
            user_id: 用户 ID（用于加载长期用户记忆）
        """
        try:
            # 1. 获取 schema
            schema = await self._get_schema()

            # 2. 构建对话历史
            history = self._build_history(messages)

            # 3. 构建上一轮查询参考（帮助 LLM 理解"X呢？"等追问）
            context_hint = self._build_context_hint(context)

            # 4. 构建用户长期记忆（偏好、习惯、常用查询等）
            user_memory_block = await self._build_user_memory(user_id)

            # 5. 构建权限约束（行级数据安全）
            permission_block = self._build_permission_prompt(user_permissions)

            # 6. LLM 生成 SQL
            prompt = NL_TO_SQL_PROMPT.format(
                schema=schema, history=history, context_hint=context_hint,
                user_memory=user_memory_block,
                permission_block=permission_block, question=query,
            )
            llm_response = await llm_client.chat(prompt)

            # 4. 提取 SQL
            sql = self._extract_sql(llm_response)

            # 5. 检查是否需要澄清
            if sql.startswith("CLARIFY:"):
                return {"status": "clarify", "message": sql[8:].strip(), "error_code": "AMBIGUOUS_INPUT"}

            # 6. 确定性列名校验：在 SQL 执行前拦截 LLM 幻觉的列名，不再依赖 LLM 纠错
            structure = await get_schema_structure()
            bad_cols = await self._validate_sql_against_schema(sql, structure)
            if bad_cols:
                return {
                    "status": "error",
                    "data": None,
                    "sql": sql,
                    "message": f"查询失败: SQL 引用了不存在的字段: {', '.join(bad_cols)}",
                    "error_code": "INVALID_COLUMN",
                }

            # 7. 执行 SQL（带错误自动修正，最多重试2次）
            max_retries = 2
            last_error = None
            for attempt in range(max_retries + 1):
                try:
                    result = await self._execute_sql(sql)
                    break
                except Exception as e:
                    last_error = str(e)
                    if attempt < max_retries:
                        logger.warning(f"SQL 执行失败（第{attempt + 1}次），尝试修正: {last_error}")
                        sql = await self._fix_sql_error(schema, query, sql, last_error)
                        if not sql:
                            raise
                    else:
                        raise

            # 8. 转换字段名为中文
            result = self._translate_fields(result)

            # 9. 生成摘要
            summary = await self._generate_summary(query, result)

            return {"status": "ok", "data": result, "sql": sql, "message": summary}

        except ValueError as e:
            return {"status": "error", "data": None, "sql": None, "message": str(e), "error_code": "INVALID_SQL"}
        except Exception as e:
            logger.error(f"查询执行失败: {e}", exc_info=True)
            err_msg = str(e) if str(e) else f"请求超时（{type(e).__name__}），请稍后重试"
            return {"status": "error", "data": None, "sql": None, "message": f"查询失败: {err_msg}", "error_code": "QUERY_ERROR"}

    async def _get_schema(self) -> str:
        if self._schema_cache is None:
            self._schema_cache = await get_summary_ddl()
        return self._schema_cache

    def _build_context_hint(self, context: dict) -> str:
        """构建上一轮查询参考，帮助 LLM 理解"X呢？"等追问模式。

        提供上一轮查询的完整上下文（用户问题 + 执行的 SQL + 结果摘要），
        让 LLM 看到追问时能沿用相同的查询结构，只需替换条件值。
        """
        last_query = context.get("last_query")
        last_sql = context.get("last_sql")
        last_result = context.get("last_result")

        if not last_query:
            return "（这是第一轮对话，无上一轮查询参考）"

        parts = [f"- 上一轮用户问题: {last_query}"]

        if last_sql:
            parts.append(f"- 上一轮执行的 SQL: {last_sql}")
        elif last_result and isinstance(last_result, dict):
            # fallback: last_result 内部也可能携带 sql
            inner_sql = last_result.get("sql")
            if inner_sql:
                parts.append(f"- 上一轮执行的 SQL: {inner_sql}")

        if last_result and isinstance(last_result, dict):
            count = last_result.get("count", 0)
            data = last_result.get("data")
            if data and isinstance(data, list) and len(data) > 0:
                sample = data[0]
                if isinstance(sample, dict):
                    fields = "、".join(list(sample.keys())[:5])
                    parts.append(f"- 上一轮结果: {count} 条，字段包括: {fields}")
                else:
                    parts.append(f"- 上一轮结果: {count} 条")
            else:
                parts.append(f"- 上一轮结果: {count} 条")

        parts.append("- 重要: 如果当前用户输入是\"X呢？\"形式的追问，" \
                     "请沿用上一轮 SQL 的查询结构，只将条件值替换为 X")

        return "\n".join(parts)

    async def _build_user_memory(self, user_id: int) -> str:
        """构建用户长期记忆上下文，注入 NL→SQL prompt。

        从 MySQL user_preferences 表读取用户的偏好/习惯/常用查询，
        帮助 LLM 理解用户的个性化表达和默认过滤条件。

        Args:
            user_id: 用户 ID

        Returns:
            str: 用户记忆上下文文本
        """
        if not user_id:
            return ""

        try:
            from app.memory.user_memory import user_memory
            prefs = await user_memory.get_user_preferences(user_id)
            if not prefs:
                return ""

            parts = []
            # 近期查询（帮助 LLM 理解用户的查询模式）
            recent = prefs.get("recent_queries") or []
            if recent:
                recent_text = "\n".join([
                    f"  - {r.get('query', '')}" for r in recent[-5:]
                ])
                parts.append(f"- 用户最近查询:\n{recent_text}")

            # 默认过滤条件
            filters = prefs.get("default_filters") or {}
            if filters:
                filter_text = ", ".join([f"{k}={v}" for k, v in filters.items()])
                parts.append(f"- 用户默认过滤: {filter_text}")

            if parts:
                return "## 用户长期记忆（个性化上下文，理解用户的表达习惯和偏好）\n" + "\n".join(parts)

        except Exception:
            pass  # 记忆加载失败不阻塞查询
        return ""

    def _build_permission_prompt(self, user_permissions: dict | None) -> str:
        """构建数据权限约束提示，注入 NL→SQL prompt 以确保行级安全。

        当用户有具体权限范围（非空列表）时，要求 LLM 在 SQL 中强制加入过滤条件。
        admin 用户权限为空（全部 warehouse_ids 为空），不加限制。

        Returns:
            str: 权限约束提示文本
        """
        if not user_permissions:
            return "（当前用户无数据权限限制，可访问所有数据）"

        warehouse_ids = user_permissions.get("warehouse_ids") or []
        region_ids = user_permissions.get("region_ids") or []
        customer_ids = user_permissions.get("customer_ids") or []
        product_ids = user_permissions.get("product_ids") or []

        constraints = []
        if warehouse_ids:
            ids_str = ", ".join(str(w) for w in warehouse_ids)
            constraints.append(
                f"- **仓库限制**：该用户只能查询 warehouse_id IN ({ids_str}) 的数据。"
                f"所有涉及仓库/库存/入库/出库的查询，**必须**在 WHERE 中加上 "
                f"warehouse_id IN ({ids_str}) 或 w.id IN ({ids_str})。"
            )
        if region_ids:
            ids_str = ", ".join(str(r) for r in region_ids)
            constraints.append(
                f"- **区域限制**：该用户只能查询 region_id IN ({ids_str}) 的数据。"
            )
        if customer_ids:
            ids_str = ", ".join(str(c) for c in customer_ids)
            constraints.append(
                f"- **客户限制**：该用户只能查询 customer_id IN ({ids_str}) 的数据（销售订单/客户相关表）。"
            )
        if product_ids:
            ids_str = ", ".join(str(p) for p in product_ids)
            constraints.append(
                f"- **商品限制**：该用户只能查询 product_id IN ({ids_str}) 的数据（商品相关表）。"
            )

        if not constraints:
            return "（当前用户无数据权限限制，可访问所有数据）"

        return "## 当前用户数据权限（**强制执行**，违反将导致越权查询错误）\n" + "\n".join(constraints)

    def _build_history(self, messages: list[dict]) -> str:
        """构建对话历史摘要，帮助 LLM 理解上下文"""
        if not messages:
            return "（这是第一轮对话，无历史）"
        history_lines = []
        # 取最近 6 轮对话（12条消息）
        for msg in messages[-12:]:
            if msg['role'] == 'user':
                role = "用户"
            elif msg['role'] == 'assistant':
                role = "AI助手"
            else:
                role = "系统"
            # 保留完整内容，不做截断（上下文对理解省略/代词至关重要）
            history_lines.append(f"{role}: {msg['content']}")
        return "\n".join(history_lines)

    def _extract_sql(self, llm_response: str) -> str:
        match = re.search(r'```(?:sql)?\s*(.*?)```', llm_response, re.DOTALL)
        if match:
            return match.group(1).strip()
        return llm_response.strip()

    async def _validate_sql_against_schema(self, sql: str, structure: dict) -> list[str]:
        """校验 SQL 引用的列名是否存在于 schema，返回不存在的列名列表（空=通过）。

        策略（简化，主要拦截明显不存在的列名）：
        - 从 FROM/JOIN 提取表名与别名
        - alias.col 形式：检查 col 是否存在于 alias 对应表
        - 裸列名（SELECT 子句）：检查是否存在于任意表
        - 跳过 COUNT(*) 等函数调用、*、alias.*、字符串字面量、SQL 关键字
        """
        bad_cols: list[str] = []

        # 去掉字符串字面量，避免误判（'' 替换单引号内的任意内容）
        sql_no_literals = re.sub(r"'(?:[^']|'')*'", "''", sql)

        # 1. 提取 FROM/JOIN 中的 表名 与 别名
        table_aliases: dict[str, str] = {}
        for m in re.finditer(
            r'(?:FROM|JOIN)\s+`?([A-Za-z_]\w*)`?(?:\s+(?:AS\s+)?([A-Za-z_]\w*))?',
            sql_no_literals, re.IGNORECASE,
        ):
            table, alias = m.group(1), m.group(2) or m.group(1)
            table_aliases[alias] = table

        # 2. alias.col 检查（全 SQL，含 WHERE/GROUP BY/ORDER BY）
        for m in re.finditer(r'([A-Za-z_]\w*)\.([A-Za-z_]\w*)', sql_no_literals):
            alias, column = m.group(1), m.group(2)
            table = table_aliases.get(alias)
            if table is None:
                continue  # 未知别名（如子查询别名），跳过
            if column not in structure.get(table, set()):
                bad_cols.append(column)

        # 3. SELECT 子句裸列名检查
        select_match = re.search(
            r'SELECT\s+(.*?)\s+FROM\b', sql_no_literals, re.IGNORECASE | re.DOTALL
        )
        if select_match:
            clause = select_match.group(1)
            # 去掉 alias.col / alias.* 与 AS 别名，剩下的才是裸列名
            clause = re.sub(r'[A-Za-z_]\w*\.(?:[A-Za-z_]\w*|\*)', ' ', clause)
            clause = re.sub(r'\bAS\s+[A-Za-z_]\w*', ' ', clause, flags=re.IGNORECASE)
            all_columns = set().union(*structure.values()) if structure else set()

            for m in re.finditer(r'[A-Za-z_]\w*', clause):
                ident = m.group(0)
                if ident.upper() in SQL_RESERVED:
                    continue
                # 前一个非空格字符是标识符/数字 → 是别名或表达式中间项，跳过
                prev = clause[:m.start()].rstrip()
                if prev and (prev[-1].isalnum() or prev[-1] == '_'):
                    continue
                if ident not in all_columns:
                    bad_cols.append(ident)

        # 去重且保持顺序
        return list(dict.fromkeys(bad_cols))

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

    async def _fix_sql_error(self, schema: str, question: str, failed_sql: str, error: str) -> str | None:
        """SQL 执行失败时，将错误信息反馈给 LLM 进行修正"""
        fix_prompt = f"""你之前生成了以下 SQL，但执行时出错。

## 数据库 Schema
{schema}

## 原始问题
{question}

## 错误的 SQL
```sql
{failed_sql}
```

## 错误信息
{error}

## 要求
请根据错误信息修正 SQL 语句。常见修正方向：
- 如果提示 "Unknown column"，说明列名不存在，请检查 schema 中该表实际有哪些列，只使用存在的列名
- 如果提示语法错误，修正语法
- 不要编造 schema 中不存在的列名！

只返回修正后的 SQL 语句，不要解释。

## SQL"""
        try:
            response = await llm_client.chat(fix_prompt)
            sql = self._extract_sql(response)
            if sql and not sql.startswith("CLARIFY:"):
                logger.info(f"LLM 修正后的 SQL: {sql}")
                return sql
        except Exception as e:
            logger.error(f"SQL 修正失败: {e}")
        return None

    async def _generate_summary(self, question: str, rows: list[dict]) -> str:
        """生成查询结果摘要。

        默认使用模板（查询到 N 条记录）；仅当配置 llm_enable_summary 为 True 时才调用 LLM。
        """
        n = len(rows)
        if n == 0:
            return "查询结果为空"
        if not settings.llm_enable_summary:
            return f"查询到 {n} 条记录"
        try:
            from app.agent.prompts import EXPLAIN_PROMPT
            prompt = EXPLAIN_PROMPT.format(question=question, result=str(rows[:10]))
            return await llm_client.chat(prompt)
        except Exception:
            return f"查询到 {n} 条记录"
