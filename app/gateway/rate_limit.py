"""速率限制中间件

基于内存的简单速率限制实现。
生产环境建议使用 Redis。
"""

import time
import logging
from collections import defaultdict

from fastapi import HTTPException, Request

logger = logging.getLogger(__name__)


class RateLimiter:
    """速率限制器

    使用滑动窗口算法。
    """

    def __init__(self, max_requests: int = 60, window_seconds: int = 60):
        """
        Args:
            max_requests: 窗口内最大请求数
            window_seconds: 窗口大小（秒）
        """
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests: dict[str, list[float]] = defaultdict(list)

    def is_allowed(self, key: str) -> bool:
        """检查请求是否允许

        Args:
            key: 限制键（通常是用户 ID 或 IP 地址）
        """
        now = time.time()
        window_start = now - self.window_seconds

        # 清理过期记录
        self.requests[key] = [
            t for t in self.requests[key]
            if t > window_start
        ]

        # 检查是否超过限制
        if len(self.requests[key]) >= self.max_requests:
            return False

        # 记录请求
        self.requests[key].append(now)
        return True

    def get_remaining(self, key: str) -> int:
        """获取剩余请求数"""
        now = time.time()
        window_start = now - self.window_seconds

        valid_requests = [
            t for t in self.requests[key]
            if t > window_start
        ]

        return max(0, self.max_requests - len(valid_requests))


# 全局速率限制器实例
rate_limiter = RateLimiter(max_requests=60, window_seconds=60)


async def check_rate_limit(request: Request):
    """检查速率限制

    基于客户端 IP 地址限制。
    """
    client_ip = request.client.host if request.client else "unknown"

    if not rate_limiter.is_allowed(client_ip):
        remaining = rate_limiter.get_remaining(client_ip)
        raise HTTPException(
            status_code=429,
            detail={
                "status": "error",
                "message": "请求过于频繁，请稍后重试",
                "error_code": "RATE_LIMITED",
                "retry_after": rate_limiter.window_seconds,
            },
        )
