"""Aggregator - 结果聚合

把多个子任务的执行结果汇总成一段连贯回答（设计文档 §24「Aggregation Layer」）。
只负责「表达/总结/解释」，禁止修改业务事实、补全不存在的数据、猜测执行结果。
"""

import logging

from app.agent.llm_client import llm_client

logger = logging.getLogger(__name__)

AGGREGATE_PROMPT = """你是企业 AI 助手的结果汇总器。把多个子任务的执行结果汇总成一段清晰连贯的回答。

## 用户原始请求
{user_input}

## 子任务执行结果
{task_results}

## 汇总要求
1. 只使用上面子任务结果中的数据，禁止编造、补全不存在的数字或事实
2. FAILED / 失败的任务要明确说明，不能声称已完成
3. 按逻辑顺序组织：先查询类结果，后写操作结果
4. 简洁清晰，不要过度展开
5. 如果所有任务都失败，诚实告知用户"""


def _format_results(step_results: list[dict]) -> str:
    """把步骤结果列表格式化成文本，供 LLM 汇总"""
    lines = []
    for i, r in enumerate(step_results, 1):
        action = r.get("action", "")
        result = r.get("result", {}) or {}
        status = result.get("status", "unknown")
        message = result.get("message", "")
        data = result.get("data")
        data_text = str(data)[:500] if data else ""
        parts = [f"【子任务{i}】action={action}，状态={status}"]
        if message:
            parts.append(f"消息: {message}")
        if data_text:
            parts.append(f"数据: {data_text}")
        lines.append("\n".join(parts))
    return "\n\n".join(lines)


class Aggregator:
    """结果聚合器"""

    async def aggregate(self, user_input: str, step_results: list[dict]) -> str:
        """汇总多个步骤结果

        Args:
            user_input: 用户原始请求
            step_results: 步骤结果列表（每个含 action/result）

        Returns:
            str: 汇总后的回答文本
        """
        task_results_text = _format_results(step_results)

        # 单步骤成功且已有 message，直接返回，避免多余 LLM 调用
        if len(step_results) == 1:
            result = step_results[0].get("result", {}) or {}
            if result.get("status") == "ok" and result.get("message"):
                return result["message"]

        prompt = AGGREGATE_PROMPT.format(user_input=user_input, task_results=task_results_text)
        try:
            response = await llm_client.chat(prompt)
            return response.strip()
        except Exception as e:
            logger.warning(f"结果聚合失败，降级拼接原始消息: {e}")
            # 降级：拼接各步骤 message
            fallback = "\n".join(
                f"• {r.get('result', {}).get('message', '')}"
                for r in step_results
                if r.get("result", {}).get("message")
            )
            return fallback or "任务已执行，但结果聚合失败"


# 全局实例
aggregator = Aggregator()
