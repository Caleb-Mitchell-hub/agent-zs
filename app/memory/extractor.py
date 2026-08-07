"""记忆抽取器

职责：
- 从对话中抽取关键信息
- 更新长期记忆
- 避免记忆库膨胀
"""

import logging
import re
from typing import Optional

from app.memory.user_memory import user_memory

logger = logging.getLogger(__name__)

# 记忆抽取规则：memory_type -> 正则模式列表
EXTRACT_PATTERNS = {
    "preference": [
        r"我喜欢[^。；]+",
        r"我习惯[^。；]+",
        r"请(?:用|按|以)[^。；]+",
        r"按老规矩[^。；]+",
    ],
    "fact": [
        r"我的(?:部门|名字|工号|职位)是[^。；]+",
        r"我是[^。；]{2,10}部门的",
        r"我们(?:公司|部门)叫[^。；]+",
    ],
    "habit": [
        r"每月[^。；]+",
        r"每周[^。；]+",
        r"每天[^。；]+",
        r"(?:月初|月末)[^。；]+",
    ],
}


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
            # 按行用正则规则抽取并保存（confidence 固定 0.8）
            saved = set()
            for line in conversation.splitlines():
                for memory_type, patterns in EXTRACT_PATTERNS.items():
                    for pattern in patterns:
                        for content in re.findall(pattern, line):
                            if (memory_type, content) in saved:
                                continue
                            saved.add((memory_type, content))
                            await user_memory.update_user_preferences(
                                user_id=user_id,
                                preferences={
                                    "memory_type": memory_type,
                                    "content": content,
                                    "source_session": session_id,
                                }
                            )
                            logger.info(f"记忆保存: {memory_type} - {content[:50]}")

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
