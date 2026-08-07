"""工具注册中心

职责：
- 统一工具注册
- 工具元数据管理
- 工具调用路由
"""

import asyncio
import inspect
import logging
from typing import Callable, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# 可重试的异常：超时与网络/IO 类错误（ConnectionError 等均继承自 OSError）
RETRYABLE_ERRORS = (asyncio.TimeoutError, OSError)


@dataclass
class ToolMetadata:
    """工具元数据"""
    name: str
    description: str
    input_schema: dict
    output_schema: dict
    permission_level: str  # low/medium/high
    risk_level: str = "medium"  # low/medium/high
    need_confirm: bool = False
    timeout: int = 30
    retry_count: int = 3
    enabled: bool = True  # 启停开关（配置中心可调）


class ToolRegistry:
    """工具注册中心"""

    def __init__(self):
        self._tools: dict[str, ToolMetadata] = {}
        self._handlers: dict[str, Callable] = {}

    def register(
        self,
        name: str,
        handler: Callable,
        description: str = "",
        input_schema: dict = None,
        output_schema: dict = None,
        permission_level: str = "medium",
        risk_level: str = "medium",
        need_confirm: bool = False,
        timeout: int = 30,
        retry_count: int = 3,
    ):
        """注册工具

        Args:
            name: 工具名称
            handler: 处理函数
            description: 描述
            input_schema: 输入 Schema
            output_schema: 输出 Schema
            permission_level: 权限等级
            risk_level: 风险等级
            need_confirm: 是否需要确认
            timeout: 超时时间
            retry_count: 重试次数
        """
        metadata = ToolMetadata(
            name=name,
            description=description,
            input_schema=input_schema or {},
            output_schema=output_schema or {},
            permission_level=permission_level,
            risk_level=risk_level,
            need_confirm=need_confirm,
            timeout=timeout,
            retry_count=retry_count,
        )

        self._tools[name] = metadata
        self._handlers[name] = handler
        logger.info(f"工具注册: {name}")

    def get_handler(self, tool_name: str) -> Optional[Callable]:
        """获取工具处理器"""
        return self._handlers.get(tool_name)

    def get_metadata(self, tool_name: str) -> Optional[ToolMetadata]:
        """获取工具元数据"""
        return self._tools.get(tool_name)

    def list_tools(self) -> list[dict]:
        """列出所有工具"""
        return [
            {
                "name": meta.name,
                "description": meta.description,
                "permission_level": meta.permission_level,
                "need_confirm": meta.need_confirm,
            }
            for meta in self._tools.values()
        ]

    def check_permission(self, tool_name: str, user_permission: str) -> bool:
        """检查权限

        Args:
            tool_name: 工具名称
            user_permission: 用户权限等级

        Returns:
            bool: 是否有权限
        """
        tool = self._tools.get(tool_name)
        if not tool:
            return False

        levels = {"low": 0, "medium": 1, "high": 2}
        return levels.get(user_permission, 0) >= levels.get(tool.permission_level, 0)

    def apply_policy(
        self,
        tool_name: str,
        enabled: bool = None,
        risk_level: str = None,
        need_confirm: bool = None,
        timeout: int = None,
        retry_count: int = None,
    ):
        """应用运营策略（配置中心/启动时调用，叠加到注册元数据）

        只覆盖传入的字段，未传的保持注册默认值。
        """
        meta = self._tools.get(tool_name)
        if not meta:
            logger.warning(f"应用策略失败，工具未注册: {tool_name}")
            return
        if enabled is not None:
            meta.enabled = enabled
        if risk_level is not None:
            meta.risk_level = risk_level
        if need_confirm is not None:
            meta.need_confirm = need_confirm
        if timeout is not None:
            meta.timeout = timeout
        if retry_count is not None:
            meta.retry_count = retry_count
        logger.info(f"工具策略已应用: {tool_name}")

    def list_tools_full(self) -> list[dict]:
        """列出工具完整策略（含 risk_level/timeout/retry_count/enabled，供配置中心展示）"""
        return [
            {
                "name": meta.name,
                "description": meta.description,
                "permission_level": meta.permission_level,
                "risk_level": meta.risk_level,
                "need_confirm": meta.need_confirm,
                "timeout": meta.timeout,
                "retry_count": meta.retry_count,
                "enabled": meta.enabled,
            }
            for meta in self._tools.values()
        ]


class ToolExecutor:
    """工具执行器：强制执行二次确认、超时控制与规则化重试

    可通过 registry 参数注入注册中心（默认使用全局 tool_registry），便于测试。
    """

    def __init__(self, registry: "ToolRegistry" = None):
        self._registry = registry or tool_registry

    async def execute_tool(
        self,
        tool_name: str,
        params: dict = None,
        confirmed: bool = False,
    ) -> dict:
        """执行工具

        执行顺序：
        1. 二次确认：need_confirm 的工具未确认时返回 waiting_confirm，不执行
        2. 超时控制：asyncio.wait_for 超时抛 asyncio.TimeoutError
        3. 规则化重试：超时/网络类错误重试 meta.retry_count 次；
           参数错误(ValueError/TypeError)不重试直接返回错误
        4. 返回结果：handler 返回 dict 则透传，否则包装为 {"status": "ok", "result": ...}

        Args:
            tool_name: 工具名称
            params: 调用参数（keyword 参数）
            confirmed: 是否已二次确认

        Returns:
            dict: 执行结果
        """
        meta = self._registry.get_metadata(tool_name)
        handler = self._registry.get_handler(tool_name)
        if meta is None or handler is None:
            return {"status": "error", "message": f"工具未注册: {tool_name}"}

        # 0. 启停开关检查（配置中心可禁用工具）
        if not meta.enabled:
            return {"status": "error", "message": f"工具已禁用: {tool_name}", "error_code": "TOOL_DISABLED"}

        # 1. 二次确认检查
        if meta.need_confirm and not confirmed:
            return {"status": "waiting_confirm", "message": f"需要确认后才执行: {tool_name}"}

        # 2 & 3. 超时控制 + 规则化重试
        for attempt in range(meta.retry_count + 1):
            try:
                result = await asyncio.wait_for(
                    self._invoke_handler(handler, params), timeout=meta.timeout
                )
                # 4. 透传 dict，否则包装
                if isinstance(result, dict):
                    return result
                return {"status": "ok", "result": result}
            except (ValueError, TypeError) as e:
                # 参数错误：不重试，直接返回
                return {"status": "error", "message": f"工具 {tool_name} 参数错误: {e}"}
            except RETRYABLE_ERRORS as e:
                if attempt < meta.retry_count:
                    logger.warning(f"工具 {tool_name} 执行失败(第{attempt + 1}次)，重试: {e}")
                    continue
                return {
                    "status": "error",
                    "message": f"工具 {tool_name} 执行失败，已重试 {meta.retry_count} 次: {e}",
                }
            except Exception as e:
                return {"status": "error", "message": f"工具 {tool_name} 执行失败: {e}"}

        # 理论不可达，兜底
        return {"status": "error", "message": f"工具 {tool_name} 执行失败"}

    async def _invoke_handler(self, handler: Callable, params: Optional[dict]):
        """调用处理器，兼容缺少 kwargs 支持及同步/异步函数"""
        if params:
            try:
                result = handler(**params)
            except TypeError:
                # handler 不支持 kwargs，退化为位置参数调用
                result = handler(*params.values())
        else:
            result = handler()
        if inspect.isawaitable(result):
            result = await result
        return result


# 全局实例
tool_registry = ToolRegistry()
