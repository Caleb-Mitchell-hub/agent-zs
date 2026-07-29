"""速率限制

职责：
- 按用户限流
- 按租户限流
- 支持配置化
"""

import time
import logging
from collections import defaultdict
from fastapi import HTTPException, Request

logger = logging.getLogger(__name__)


class RateLimiter:
    """速率限制器（滑动窗口）"""

    def __init__(self):
        self._requests: dict[str, list[float]] = defaultdict(list)
        # 默认配置
        self.configs = {
            "default": {"max_requests": 60, "window_seconds": 60},
            "user": {"max_requests": 120, "window_seconds": 60},
            "tenant": {"max_requests": 1000, "window_seconds": 60},
        }

    def is_allowed(self, key: str, config_type: str = "default") -> tuple[bool, int]:
        """检查是否允许

        Args:
            key: 限制键
            config_type: 配置类型

        Returns:
            tuple: (是否允许, 剩余请求数)
        """
        config = self.configs.get(config_type, self.configs["default"])
        max_requests = config["max_requests"]
        window_seconds = config["window_seconds"]

        now = time.time()
        window_start = now - window_seconds

        # 清理过期记录
        self._requests[key] = [t for t in self._requests[key] if t > window_start]

        # 检查限制
        remaining = max_requests - len(self._requests[key])
        if remaining <= 0:
            return False, 0

        # 记录请求
        self._requests[key].append(now)
        return True, remaining - 1

    def get_user_key(self, user_id: str, tenant_id: str) -> str:
        """获取用户限流键"""
        return f"user:{tenant_id}:{user_id}"

    def get_tenant_key(self, tenant_id: str) -> str:
        """获取租户限流键"""
        return f"tenant:{tenant_id}"


# 全局实例
rate_limiter = RateLimiter()


async def check_rate_limit(request: Request):
    """检查速率限制"""
    # 从请求中获取用户信息（简化实现）
    tenant_id = "1"
    user_id = "1"

    # 检查用户限流
    user_key = rate_limiter.get_user_key(user_id, tenant_id)
    allowed, remaining = rate_limiter.is_allowed(user_key, "user")

    if not allowed:
        raise HTTPException(
            status_code=429,
            detail={"status": "error", "message": "请求过于频繁，请稍后重试", "error_code": "RATE_LIMITED"},
        )

    # 检查租户限流
    tenant_key = rate_limiter.get_tenant_key(tenant_id)
    allowed, _ = rate_limiter.is_allowed(tenant_key, "tenant")

    if not allowed:
        raise HTTPException(
            status_code=429,
            detail={"status": "error", "message": "租户请求配额已用完", "error_code": "TENANT_LIMITED"},
        )
