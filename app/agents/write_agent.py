"""Write Agent - 业务写操作 Agent

职责：
- 创建单据
- 更新单据状态

工具：
- ERP API Tool
- Audit Tool
"""

import logging
from typing import Optional

from app.tools.erp_api_tool import ErpApiTool
from app.memory import session_memory

logger = logging.getLogger(__name__)


class WriteAgent:
    """业务写操作 Agent"""

    def __init__(self):
        self.erp_tool = ErpApiTool()

    async def execute(
        self,
        user_input: str,
        messages: list[dict],
        context: dict,
        session_id: str,
        user_id: int,
        tenant_id: int,
    ) -> dict:
        """执行写操作任务

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
            # 1. 解析用户意图，提取单据类型和参数
            doc_info = await self._parse_document_info(user_input, messages)

            if not doc_info:
                return {
                    "status": "clarify",
                    "message": "请提供更多信息：您想创建什么类型的单据？",
                    "error_code": "AMBIGUOUS_INPUT",
                }

            # 2. 使用 ERP API Tool 执行操作
            result = await self.erp_tool.execute(
                action=doc_info["action"],
                doc_type=doc_info["doc_type"],
                params=doc_info["params"],
                user_id=user_id,
                tenant_id=tenant_id,
            )

            # 3. 更新上下文
            await session_memory.update_context(session_id, {
                "last_action": doc_info["action"],
                "last_doc_type": doc_info["doc_type"],
                "last_doc_id": result.get("doc_id"),
            })

            return result

        except Exception as e:
            logger.error(f"Write Agent 执行失败: {e}", exc_info=True)
            return {
                "status": "error",
                "message": f"操作执行失败: {str(e)}",
                "error_code": "WRITE_AGENT_ERROR",
            }

    async def _parse_document_info(self, user_input: str, messages: list[dict]) -> Optional[dict]:
        """解析用户输入，提取单据信息

        Args:
            user_input: 用户输入
            messages: 历史消息

        Returns:
            Optional[dict]: 单据信息，包含 action, doc_type, params
        """
        user_input_lower = user_input.lower()

        # 判断操作类型
        action = "create"
        if any(kw in user_input_lower for kw in ["更新", "修改", "审批", "提交"]):
            action = "update"

        # 判断单据类型
        doc_type = None
        if any(kw in user_input_lower for kw in ["采购", "采购订单"]):
            doc_type = "purchase_order"
        elif any(kw in user_input_lower for kw in ["销售", "销售订单"]):
            doc_type = "sales_order"
        elif any(kw in user_input_lower for kw in ["入库", "入库单"]):
            doc_type = "stock_in_order"
        elif any(kw in user_input_lower for kw in ["出库", "出库单"]):
            doc_type = "stock_out_order"

        if not doc_type:
            return None

        return {
            "action": action,
            "doc_type": doc_type,
            "params": {"user_input": user_input},
        }
