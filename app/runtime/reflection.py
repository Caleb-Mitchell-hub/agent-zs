"""Agent 自我纠错/反思机制

职责：
- 工具调用失败时反思重试
- 调整参数或换查询方式
- 连续失败转人工介入
"""

import logging
from typing import Optional, Callable

logger = logging.getLogger(__name__)


class ReflectionEngine:
    """反思引擎"""

    def __init__(self):
        self.max_retries = 3
        self._retry_counts: dict[str, int] = {}

    async def should_retry(self, task_id: str, step_id: str, error: str) -> bool:
        """判断是否应该重试

        Args:
            task_id: 任务ID
            step_id: 步骤ID
            error: 错误信息

        Returns:
            bool: 是否应该重试
        """
        key = f"{task_id}_{step_id}"
        count = self._retry_counts.get(key, 0)

        if count >= self.max_retries:
            logger.warning(f"重试次数已达上限: {key}, 转人工介入")
            return False

        self._retry_counts[key] = count + 1
        logger.info(f"反思重试: {key}, 第 {count + 1} 次")
        return True

    async def reflect_and_fix(self, error: str, original_params: dict) -> dict:
        """反思并修复参数

        Args:
            error: 错误信息
            original_params: 原始参数

        Returns:
            dict: 修复后的参数
        """
        fixed_params = original_params.copy()

        # 常见错误修复策略
        if "找不到" in error or "不存在" in error:
            # 可能是字段名不匹配，尝试添加模糊搜索
            if "name" in fixed_params:
                fixed_params["name"] = f"%{fixed_params['name']}%"
                logger.info(f"反思修复: 添加模糊搜索")

        elif "超时" in error:
            # 超时错误，减少返回数量
            if "limit" in fixed_params:
                fixed_params["limit"] = min(fixed_params["limit"], 10)
                logger.info(f"反思修复: 减少返回数量")

        elif "权限" in error:
            # 权限错误，记录并返回
            logger.warning(f"权限不足，需要人工介入")
            return None

        return fixed_params


# 全局实例
reflection_engine = ReflectionEngine()
