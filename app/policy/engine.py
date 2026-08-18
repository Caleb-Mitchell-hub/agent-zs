"""Policy Engine - RBAC/ABAC 权限与风险判定

在任务计划执行前，对每个 action 做确定性判定（设计文档 §21「Policy Engine」、§22「RBAC+ABAC」）：
LLM 只提出「我要做什么」，真正是否允许执行由本模块决定，不依赖 Prompt 控制。

数据范围（ABAC）已在 JWT → user_permissions → data_agent 通道中实现，
本模块提供 build_user_permissions() 统一打包。
"""

import logging
from enum import Enum

logger = logging.getLogger(__name__)


class PolicyDecision(str, Enum):
    """策略判定结果"""
    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_CONFIRMATION = "require_confirmation"


# 写操作 action（需要写权限）
_WRITE_ACTIONS = {"create", "update"}

# 高风险 action（强制人工确认，不由 LLM 决定）
_HIGH_RISK_ACTIONS = {"update"}

# 具备写权限的角色码（与 sys_role.role_code 对应；is_super_admin 恒放行）
_WRITE_ROLE_CODES = {"admin", "write", "manager"}


def evaluate_policy(action: str, user_info: dict | None) -> PolicyDecision:
    """判定单个 action 的执行策略

    Args:
        action: 能力名（query/create/update/report/knowledge）
        user_info: 用户信息（含 is_super_admin/roles）

    Returns:
        PolicyDecision: ALLOW / DENY / REQUIRE_CONFIRMATION
    """
    user_info = user_info or {}
    is_admin = bool(user_info.get("is_super_admin"))
    roles = set(user_info.get("roles") or [])

    # 1. 写操作权限检查（RBAC）
    if action in _WRITE_ACTIONS:
        has_write = is_admin or bool(roles & _WRITE_ROLE_CODES)
        if not has_write:
            logger.warning(f"Policy 拒绝写操作 {action}: 用户无写权限 (roles={roles})")
            return PolicyDecision.DENY

    # 2. 高风险强制确认
    if action in _HIGH_RISK_ACTIONS:
        return PolicyDecision.REQUIRE_CONFIRMATION

    return PolicyDecision.ALLOW


def build_user_permissions(user_info: dict | None) -> dict:
    """从用户信息构建数据范围权限（ABAC），供 data_agent 注入

    Args:
        user_info: 用户信息（含 warehouse_ids/region_ids/customer_ids/product_ids）

    Returns:
        dict: 数据范围 ID 列表
    """
    user_info = user_info or {}
    return {
        "warehouse_ids": user_info.get("warehouse_ids") or [],
        "region_ids": user_info.get("region_ids") or [],
        "customer_ids": user_info.get("customer_ids") or [],
        "product_ids": user_info.get("product_ids") or [],
    }
