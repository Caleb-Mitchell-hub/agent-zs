"""工具注册中心

职责：
- 统一工具注册
- 工具元数据管理
- 工具调用路由
"""

import logging
from typing import Callable, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ToolMetadata:
    """工具元数据"""
    name: str
    description: str
    input_schema: dict
    output_schema: dict
    permission_level: str  # low/medium/high
    need_confirm: bool = False
    timeout: int = 30
    retry_count: int = 3


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


# 全局实例
tool_registry = ToolRegistry()
