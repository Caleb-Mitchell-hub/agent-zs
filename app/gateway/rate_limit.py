"""速率限制

职责：
- 按用户限流
- 按租户限流
- 支持配置化
"""

import time
import logging
from collections import defaultdict
from fastapi import Depends, HTTPException, Request

from app.gateway.auth import verify_token

logger = logging.getLogger(__name__)


class RateLimiter:
    """速率限制器（滑动窗口）"""

    def __init__(self):
        self._requests: dict[str, list[float]] = defaultdict(list)
        # 默认配置（可被配置中心覆盖）
        self.configs = {
            "default": {"max_requests": 60, "window_seconds": 60},
            "user": {"max_requests": 120, "window_seconds": 60},
            "tenant": {"max_requests": 1000, "window_seconds": 60},
        }

    async def load_from_config(self):
        """从配置中心加载限流档位（启动时 + 配置变更后调用）

        default 档来自 app_config 的 rate_limit.default；
        user/tenant 档可被 rate_limit_config 表命中覆盖（scope_type 匹配）。
        """
        try:
            from app.config_center.service import config_service

            default_cfg = await config_service.get_config("rate_limit.default", {})
            if default_cfg and isinstance(default_cfg, dict):
                self.configs["default"] = {
                    "max_requests": int(default_cfg.get("max_requests", 60)),
                    "window_seconds": int(default_cfg.get("window_seconds", 60)),
                }

            limits = await config_service.list_rate_limits()
            for item in limits:
                if not item.get("enabled", True):
                    continue
                scope_type = item.get("scope_type")
                if scope_type not in ("user", "tenant", "department"):
                    continue
                self.configs[scope_type] = {
                    "max_requests": int(item.get("qps", 10)),
                    "window_seconds": 60,
                }
            logger.info(f"限流配置已从配置中心加载: {self.configs}")
        except Exception as e:
            logger.warning(f"加载限流配置失败，使用默认值: {e}")

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


async def check_rate_limit(
    request: Request,
    user_info: dict = Depends(verify_token),
):
    """检查速率限制"""
    # 从请求中获取用户信息（简化实现）
    tenant_id = str(user_info.get("tenant_id") or "anonymous")
    user_id = str(user_info.get("user_id") or "anonymous")

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
