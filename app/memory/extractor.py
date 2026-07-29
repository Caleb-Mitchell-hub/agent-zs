"""记忆抽取器

职责：
- 从对话中抽取关键信息
- 更新长期记忆
- 避免记忆库膨胀
"""

import logging
import json
import re
from typing import Optional

from app.agent.llm_client import llm_client
from app.memory.user_memory import user_memory

logger = logging.getLogger(__name__)

# 记忆抽取 Prompt
EXTRACT_PROMPT = """你是一个记忆抽取专家。从对话中抽取值得长期记忆的关键信息。

## 对话内容
{conversation}

## 抽取类别
- preference: 用户偏好（如"我喜欢用表格展示"、"按老规矩报销"）
- fact: 事实信息（如用户部门、常用供应商）
- habit: 行为习惯（如"每月月初出报表"）

## 输出格式
返回 JSON 数组，每个元素：
{{
    "type": "preference/fact/habit",
    "content": "记忆内容",
    "confidence": 0.0-1.0
}}

如果没有值得记忆的信息，返回空数组 []

## JSON"""


class MemoryExtractor:
    """记忆抽取器"""

    async def extract_and_save(self, conversation: str, user_id: str, tenant_id: str, session_id: str):
        """抽取并保存记忆

        Args:
            conversation: 对话内容
            user_id: 用户ID
            tenant_id: 租户ID
            session_id: 会话ID
        """
        try:
            # 1. 调用 LLM 抽取记忆
            prompt = EXTRACT_PROMPT.format(conversation=conversation)
            response = await llm_client.chat(prompt)

            # 2. 解析结果
            match = re.search(r'\[.*\]', response, re.DOTALL)
            if not match:
                return

            memories = json.loads(match.group())

            # 3. 保存到长期记忆
            for memory in memories:
                if memory.get("confidence", 0) >= 0.7:
                    await user_memory.update_user_preferences(
                        user_id=user_id,
                        preferences={
                            "memory_type": memory.get("type"),
                            "content": memory.get("content"),
                            "source_session": session_id,
                        }
                    )
                    logger.info(f"记忆保存: {memory.get('type')} - {memory.get('content')[:50]}")

        except Exception as e:
            logger.warning(f"记忆抽取失败: {e}")

    async def should_extract(self, messages: list[dict]) -> bool:
        """判断是否应该抽取记忆

        Args:
            messages: 消息列表

        Returns:
            bool: 是否应该抽取
        """
        # 每 10 条消息抽取一次
        if len(messages) % 10 == 0 and len(messages) > 0:
            return True

        # 会话结束时抽取
        # 这里需要外部调用时判断

        return False


# 全局实例
memory_extractor = MemoryExtractor()
