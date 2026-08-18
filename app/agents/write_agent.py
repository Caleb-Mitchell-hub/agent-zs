"""Write Agent - 业务写操作 Agent

职责：
- 解析单据创建意图
- 提取参数
- 校验必填字段
- 调用 ERP 创建单据
"""

import re
import uuid
import json
import logging
from typing import Optional

from app.adapter.erp_adapter import erp_adapter
from app.agent.llm_client import llm_client
from app.memory import session_memory
from app.policy.engine import has_permission, DOC_TYPE_ADD_PERMISSION

logger = logging.getLogger(__name__)

# 支持的单据类型和必填字段
DOC_TYPE_FIELDS = {
    "purchase_order": {
        "name": "采购订单",
        "required": ["supplier_name", "warehouse_name", "order_date"],
        "optional": ["total_amount", "remark"],
    },
    "sales_order": {
        "name": "销售订单",
        "required": ["customer_name", "warehouse_name", "order_date"],
        "optional": ["total_amount", "remark"],
    },
    "stock_in_order": {
        "name": "入库单",
        "required": ["warehouse_name", "in_type"],
        "optional": ["source_no", "remark"],
    },
    "stock_out_order": {
        "name": "出库单",
        "required": ["warehouse_name", "out_type"],
        "optional": ["source_no", "remark"],
    },
    "expense_reimbursement": {
        "name": "报销单",
        "required": ["expense_type", "amount", "expense_date"],
        "optional": ["description", "attachment"],
    },
}

EXTRACT_PARAMS_PROMPT = """你是一个 ERP 参数提取专家。根据用户输入提取创建单据所需参数。

【对话上下文】
{context_block}

支持的单据类型：
- purchase_order: 采购订单
- sales_order: 销售订单
- stock_in_order: 入库单
- stock_out_order: 出库单
- expense_reimbursement: 报销单

【重要】如果对话上下文中用户刚做完数据查询，当前输入很可能是在追问/细化查询结果，而非创建单据。只有当用户明确表达"创建""新建""开单"等意图时，才提取单据参数。

用户输入: {user_input}

返回 JSON:
{{
    "doc_type": "单据类型",
    "params": {{
        "字段名": "值"
    }}
}}

只返回 JSON，不要解释。"""


class WriteAgent:
    """写操作 Agent"""

    async def execute(self, user_input: str, messages: list[dict], context: dict,
                      session_id: str, user_id: int, tenant_id: int,
                      user_permissions: dict | None = None) -> dict:
        try:
            # 1. 构建对话上下文
            context_block = self._build_context_block(messages, context)

            # 2. 提取参数
            prompt = EXTRACT_PARAMS_PROMPT.format(
                user_input=user_input,
                context_block=context_block,
            )
            response = await llm_client.chat(prompt)
            logger.info(f"LLM 响应: {response}")

            # 解析 JSON（更健壮的解析）
            try:
                # 尝试直接解析
                doc_info = json.loads(response)
            except:
                # 尝试提取 JSON 块
                match = re.search(r'```(?:json)?\s*(.*?)```', response, re.DOTALL)
                if match:
                    try:
                        doc_info = json.loads(match.group(1).strip())
                    except:
                        # 尝试提取 {...} 部分
                        match = re.search(r'\{.*\}', response, re.DOTALL)
                        if match:
                            doc_info = json.loads(match.group())
                        else:
                            return {
                                "status": "error",
                                "message": "无法理解您的请求，请重新描述",
                            }
                else:
                    return {
                        "status": "error",
                        "message": "无法理解您的请求，请重新描述",
                    }

            doc_type = doc_info.get("doc_type")
            params = doc_info.get("params", {})

            # 字段名映射（LLM 可能返回不同的字段名）
            field_aliases = {
                "date": "expense_date",
                "expense_date": "expense_date",
                "费用日期": "expense_date",
            }
            for key, value in list(params.items()):
                if key in field_aliases:
                    params[field_aliases[key]] = value

            # 2. 验证单据类型
            if not doc_type or doc_type not in DOC_TYPE_FIELDS:
                supported = "、".join([v["name"] for v in DOC_TYPE_FIELDS.values()])
                return {
                    "status": "clarify",
                    "message": f"不支持的单据类型，目前支持：{supported}",
                }

            doc_config = DOC_TYPE_FIELDS[doc_type]

            # 2.5 权限校验：doc_type → ADD 权限码（后端 ERP 权限码驱动，非自定义角色）
            need_code = DOC_TYPE_ADD_PERMISSION.get(doc_type)
            if need_code and user_permissions is not None:
                perm_codes = user_permissions.get("perm_codes")
                is_admin = user_permissions.get("is_super_admin", False)
                if not has_permission(perm_codes, is_admin, need_code):
                    logger.warning(f"权限拦截：缺少 {need_code} 权限，拒绝创建 {doc_config['name']}")
                    return {
                        "status": "denied",
                        "message": f"无权限创建{doc_config['name']}（缺少权限码 {need_code}）",
                        "error_code": "PERMISSION_DENIED",
                    }

            # 3. 校验必填字段
            missing_fields = []
            for field in doc_config["required"]:
                if not params.get(field):
                    field_names = {
                        "supplier_name": "供应商名称",
                        "customer_name": "客户名称",
                        "warehouse_name": "仓库名称",
                        "order_date": "订单日期（如：今天、明天、2026-01-01）",
                        "in_type": "入库类型（如：采购入库、退货入库）",
                        "out_type": "出库类型（如：销售出库、领料出库）",
                        "expense_type": "报销类型（如：差旅费、办公费、招待费）",
                        "amount": "报销金额",
                        "expense_date": "费用发生日期",
                        "description": "费用说明",
                    }
                    missing_fields.append(field_names.get(field, field))

            if missing_fields:
                return {
                    "status": "clarify",
                    "message": f"创建{doc_config['name']}需要以下信息：\n" + "\n".join([f"• {f}" for f in missing_fields]),
                }

            # 4. 通过 ERP Adapter 创建单据
            idempotency_key = f"task-{uuid.uuid4().hex[:8]}"
            result = await erp_adapter.create_document(
                doc_type=doc_type,
                params=params,
                idempotency_key=idempotency_key,
                user_id=str(user_id),
                tenant_id=str(tenant_id),
            )

            if result.get("status") == "ok":
                # 5. 返回成功信息
                doc_no = result.get("doc_no", "")
                detail_parts = []
                for k, v in params.items():
                    if v:
                        field_names = {
                            "supplier_name": "供应商",
                            "customer_name": "客户",
                            "warehouse_name": "仓库",
                            "order_date": "日期",
                            "total_amount": "金额",
                            "remark": "备注",
                            "in_type": "入库类型",
                            "out_type": "出库类型",
                        }
                        detail_parts.append(f"{field_names.get(k, k)}: {v}")

                return {
                    "status": "ok",
                    "message": f"{doc_config['name']}创建成功\n单据编号: {doc_no}\n" + "\n".join(detail_parts),
                    "doc_no": doc_no,
                    "doc_type": doc_type,
                }
            else:
                return result

        except Exception as e:
            logger.error(f"Write Agent 失败: {e}", exc_info=True)
            return {"status": "error", "message": f"创建失败: {str(e)}"}

    @staticmethod
    def _build_context_block(messages: list[dict], context: dict) -> str:
        """构建对话上下文块，帮助 WriteAgent 区分"创建单据"和"追问数据"。"""
        parts = []
        if messages:
            recent = messages[-10:]
            history = "\n".join([
                f"{'用户' if m['role'] == 'user' else 'AI'}: {m['content'][:200]}"
                for m in recent
            ])
            parts.append(f"最近对话:\n{history}")

        last_result = context.get("last_result")
        if last_result and isinstance(last_result, dict):
            last_query = context.get("last_query", "")
            if last_query:
                parts.append(f"上一轮是数据查询: {last_query}")

        return "\n\n".join(parts) if parts else "（无上下文）"
