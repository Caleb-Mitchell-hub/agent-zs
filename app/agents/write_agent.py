"""Write Agent - 业务写操作 Agent

职责：
- 创建单据
- 更新单据状态

工具：
- ERP API Tool
- Audit Tool
"""

import json
import logging
from typing import Optional

from app.tools.erp_api_tool import ErpApiTool
from app.agent.llm_client import llm_client
from app.memory import session_memory

logger = logging.getLogger(__name__)


# 参数提取 Prompt
EXTRACT_PARAMS_PROMPT = """你是一个 ERP 系统参数提取专家。根据用户的自然语言输入，提取创建单据所需的参数。

## 用户输入
{user_input}

## 对话历史
{history}

## 支持的单据类型
- purchase_order: 采购订单（需要：供应商ID、仓库ID、订单日期）
- sales_order: 销售订单（需要：客户ID、仓库ID、订单日期）
- stock_in_order: 入库单（需要：仓库ID、入库类型）
- stock_out_order: 出库单（需要：仓库ID、出库类型）

## 输出格式
返回 JSON 格式：
{{
    "action": "create" 或 "update",
    "doc_type": "单据类型",
    "params": {{
        "字段名": "值"
    }},
    "missing_fields": ["缺少的必填字段"],
    "clarify_question": "如果信息不足，需要反问用户的问题"
}}

如果信息完整，missing_fields 为空数组，clarify_question 为空字符串。
如果信息不足，missing_fields 列出缺少的字段，clarify_question 提供反问问题。

## JSON"""


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
            # 1. 使用 LLM 提取参数
            doc_info = await self._extract_params(user_input, messages)

            if not doc_info:
                return {
                    "status": "error",
                    "message": "无法理解您的请求，请重新描述",
                    "error_code": "PARSE_ERROR",
                }

            # 2. 检查是否需要澄清
            if doc_info.get("clarify_question"):
                return {
                    "status": "clarify",
                    "message": doc_info["clarify_question"],
                    "error_code": "AMBIGUOUS_INPUT",
                }

            # 3. 检查是否有缺少的必填字段
            if doc_info.get("missing_fields"):
                missing = ", ".join(doc_info["missing_fields"])
                return {
                    "status": "clarify",
                    "message": f"请提供以下信息：{missing}",
                    "error_code": "MISSING_FIELDS",
                }

            # 4. 执行操作
            action = doc_info.get("action", "create")
            doc_type = doc_info.get("doc_type")
            params = doc_info.get("params", {})

            if not doc_type:
                return {
                    "status": "error",
                    "message": "无法识别单据类型",
                    "error_code": "INVALID_DOC_TYPE",
                }

            result = await self.erp_tool.execute(
                action=action,
                doc_type=doc_type,
                params=params,
                user_id=user_id,
                tenant_id=tenant_id,
            )

            # 5. 更新上下文
            await session_memory.update_context(session_id, {
                "last_action": action,
                "last_doc_type": doc_type,
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

    async def _extract_params(self, user_input: str, messages: list[dict]) -> Optional[dict]:
        """使用 LLM 提取参数

        Args:
            user_input: 用户输入
            messages: 历史消息

        Returns:
            Optional[dict]: 提取的参数
        """
        try:
            # 构建对话历史
            history = self._build_history(messages)

            # 构建 prompt
            prompt = EXTRACT_PARAMS_PROMPT.format(
                user_input=user_input,
                history=history,
            )

            # 调用 LLM
            response = await llm_client.chat(prompt)

            # 解析 JSON
            # 尝试提取 JSON
            import re
            json_match = re.search(r'```(?:json)?\s*(.*?)```', response, re.DOTALL)
            if json_match:
                json_str = json_match.group(1).strip()
            else:
                json_str = response.strip()

            return json.loads(json_str)

        except json.JSONDecodeError as e:
            logger.error(f"JSON 解析失败: {e}")
            return None

        except Exception as e:
            logger.error(f"参数提取失败: {e}", exc_info=True)
            return None

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
