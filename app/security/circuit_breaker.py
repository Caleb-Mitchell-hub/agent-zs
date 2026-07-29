"""熔断机制

职责：
- 监控工具调用成功率
- 自动熔断异常工具
- 自动恢复
"""

import time
import logging
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class CircuitState(str, Enum):
    """熔断状态"""
    CLOSED = "closed"  # 正常
    OPEN = "open"  # 熔断
    HALF_OPEN = "half_open"  # 半开


class CircuitBreaker:
    """熔断器"""

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        success_threshold: int = 3,
    ):
        """
        Args:
            failure_threshold: 失败次数阈值
            recovery_timeout: 恢复超时（秒）
            success_threshold: 半开状态下成功次数阈值
        """
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.success_threshold = success_threshold

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time = 0

    @property
    def state(self) -> CircuitState:
        """获取当前状态"""
        if self._state == CircuitState.OPEN:
            # 检查是否可以进入半开状态
            if time.time() - self._last_failure_time > self.recovery_timeout:
                self._state = CircuitState.HALF_OPEN
                self._success_count = 0
                logger.info("熔断器进入半开状态")

        return self._state

    def can_execute(self) -> bool:
        """是否可以执行"""
        state = self.state
        return state in [CircuitState.CLOSED, CircuitState.HALF_OPEN]

    def record_success(self):
        """记录成功"""
        if self._state == CircuitState.HALF_OPEN:
            self._success_count += 1
            if self._success_count >= self.success_threshold:
                self._state = CircuitState.CLOSED
                self._failure_count = 0
                logger.info("熔断器恢复正常")
        elif self._state == CircuitState.CLOSED:
            self._failure_count = 0

    def record_failure(self):
        """记录失败"""
        self._failure_count += 1
        self._last_failure_time = time.time()

        if self._state == CircuitState.HALF_OPEN:
            self._state = CircuitState.OPEN
            logger.warning("熔断器重新打开")
        elif self._failure_count >= self.failure_threshold:
            self._state = CircuitState.OPEN
            logger.warning(f"熔断器打开，失败次数: {self._failure_count}")

    def reset(self):
        """重置熔断器"""
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0


class CircuitBreakerManager:
    """熔断器管理器"""

    def __init__(self):
        self._breakers: dict[str, CircuitBreaker] = {}

    def get_breaker(self, tool_name: str) -> CircuitBreaker:
        """获取工具的熔断器"""
        if tool_name not in self._breakers:
            self._breakers[tool_name] = CircuitBreaker()
        return self._breakers[tool_name]

    def can_execute(self, tool_name: str) -> bool:
        """检查工具是否可以执行"""
        return self.get_breaker(tool_name).can_execute()

    def record_success(self, tool_name: str):
        """记录工具调用成功"""
        self.get_breaker(tool_name).record_success()

    def record_failure(self, tool_name: str):
        """记录工具调用失败"""
        self.get_breaker(tool_name).record_failure()

    def get_status(self) -> dict:
        """获取所有熔断器状态"""
        return {
            name: {
                "state": breaker.state.value,
                "failure_count": breaker._failure_count,
            }
            for name, breaker in self._breakers.items()
        }


# 全局实例
circuit_breaker_manager = CircuitBreakerManager()
