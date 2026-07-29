"""Write Agent - 业务写操作 Agent

职责：
- 解析单据创建意图
- 提取参数
- 调用 ERP 创建单据
"""

import json
import logging
from typing import Optional

from app.adapter.erp_adapter import erp_adapter
from app.agent.llm_client import llm_client
from app.memory import session_memory

logger = logging.getLogger(__name__)

EXTRACT_PARAMS_PROMPT = """你是一个 ERP 参数提取专家。根据用户输入提取创建单据所需参数。

用户输入: {user_input}

返回 JSON:
{{
    "doc_type": "purchase_order/sales_order/stock_in_order/stock_out_order",
    "params": {{"字段名": "值"}}
}}

只返回 JSON，不要解释。"""


class WriteAgent:
    """写操作 Agent"""

    async def execute(self, user_input: str, messages: list[dict], context: dict,
                      session_id: str, user_id: int, tenant_id: int) -> dict:
        try:
            # 1. 提取参数
            prompt = EXTRACT_PARAMS_PROMPT.format(user_input=user_input)
            response = await llm_client.chat(prompt)

            # 解析 JSON
            match = re.search(r'\{.*\}', response, re.DOTALL)
            if match:
                doc_info = json.loads(match.group())
            else:
                return {"status": "error", "message": "无法理解您的请求"}

            doc_type = doc_info.get("doc_type")
            params = doc_info.get("params", {})

            if not doc_type:
                return {"status": "error", "message": "无法识别单据类型"}

            # 2. 通过 ERP Adapter 创建单据
            idempotency_key = f"task-{uuid.uuid4().hex[:8]}"
            result = await erp_adapter.create_document(
                doc_type=doc_type,
                params=params,
                idempotency_key=idempotency_key,
                user_id=str(user_id),
                tenant_id=str(tenant_id),
            )

            # 3. 更新上下文
            await session_memory.update_context(session_id, {
                "last_doc_type": doc_type,
                "last_doc_id": result.get("doc_no"),
            })

            return result

        except Exception as e:
            logger.error(f"Write Agent 失败: {e}", exc_info=True)
            return {"status": "error", "message": str(e)}


import re
import uuid
