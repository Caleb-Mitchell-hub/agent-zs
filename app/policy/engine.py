"""Policy Engine - 后端 ERP 权限码驱动的权限与风险判定

权限判定完全由后端 ERP 返回的权限码（perm_code）决定，**不在 Agent-Zs 代码里
自定义角色集合**。权限码经「用户 → 角色 → 权限」链路在登录时加载进 JWT 的
permissions 字段（super_admin 为 None 表示无限制）。

权限校验下沉到「业务对象确定后」两层：
- 查询：SQL 生成后按「表名 → VIEW 权限码」校验（database_tool）
- 创建：doc_type 确定后按「doc_type → ADD 权限码」校验（write_agent）

本模块提供：
- has_permission()：判断用户是否拥有指定权限码
- evaluate_policy()：高风险操作强制人工确认（风险控制层，非权限判定）
- 权限码映射表：TABLE_VIEW_PERMISSION（表名 → VIEW 权限码）、
  DOC_TYPE_ADD_PERMISSION（doc_type → ADD 权限码）

数据范围（ABAC）已在 JWT → user_permissions → data_agent 通道中实现，
build_user_permissions() 统一打包。
"""

import logging
from enum import Enum

logger = logging.getLogger(__name__)


class PolicyDecision(str, Enum):
    """策略判定结果"""
    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_CONFIRMATION = "require_confirmation"


# ─────────────────────────── 权限码映射表 ───────────────────────────
#
# 权限码命名规则：{业务对象}_{操作}，操作后缀 _VIEW(查)/_ADD(增)/_EDIT(改)/_DELETE(删)。
# 明细表（*_item）跟随主单的 VIEW 权限码，避免过度拆细导致误伤。

# 表名 → VIEW 权限码（查询用）。未映射的表（如 supplier 等无 button 权限码的菜单级
# 业务）不做表级权限校验，数据隔离仍由 ABAC 数据范围兜底。
TABLE_VIEW_PERMISSION = {
    # 销售
    "sales_order": "SALES_ORDER_VIEW",
    "sales_order_item": "SALES_ORDER_VIEW",
    # 采购
    "purchase_order": "PURCHASE_ORDER_VIEW",
    "purchase_order_item": "PURCHASE_ORDER_VIEW",
    # 库存
    "inventory": "INVENTORY_VIEW",
    "inventory_record": "INVENTORY_VIEW",
    "inventory_log": "INVENTORY_VIEW",
    # 主数据
    "warehouse": "WAREHOUSE_VIEW",
    "customer": "CUSTOMER_VIEW",
    "product": "PRODUCT_VIEW",
    "product_sku": "PRODUCT_VIEW",
    "product_category": "PRODUCT_VIEW",
    # 出入库
    "stock_in_order": "STOCK_IN_VIEW",
    "stock_in_order_item": "STOCK_IN_VIEW",
    "stock_out_order": "STOCK_OUT_VIEW",
    "stock_out_order_item": "STOCK_OUT_VIEW",
    "stock_transfer_order": "STOCK_TRANSFER_VIEW",
    "stock_transfer_order_item": "STOCK_TRANSFER_VIEW",
    # 报销
    "expense_reimbursement": "EXPENSE_VIEW",
}

# doc_type → ADD 权限码（创建单据用）
DOC_TYPE_ADD_PERMISSION = {
    "purchase_order": "PURCHASE_ORDER_ADD",
    "sales_order": "SALES_ORDER_ADD",
    "stock_in_order": "STOCK_IN_ADD",
    "stock_out_order": "STOCK_OUT_ADD",
    "expense_reimbursement": "EXPENSE_ADD",
}


def has_permission(perm_codes: list[str] | None, is_super_admin: bool, perm_code: str) -> bool:
    """判断用户是否拥有指定权限码

    Args:
        perm_codes: 用户权限码列表；super_admin 为 None 表示无限制
        is_super_admin: 是否超级管理员
        perm_code: 目标权限码

    Returns:
        bool: 是否拥有该权限。超级管理员恒 True；无权限信息（None 且非 admin）恒 False。
    """
    if is_super_admin:
        return True
    if perm_codes is None:
        return False  # 无权限信息，安全默认拒绝
    return perm_code in perm_codes


def evaluate_policy(action: str, user_info: dict | None = None) -> PolicyDecision:
    """高风险操作强制人工确认（风险控制层，非权限判定）

    权限判定已下沉到业务对象层（has_permission）：
    - 查询：SQL 生成后按「表名 → VIEW 权限码」校验（database_tool）
    - 创建：doc_type 确定后按「doc_type → ADD 权限码」校验（write_agent）

    本函数只保留与业务对象无关的风险控制：update 属高风险，强制人工确认。

    Args:
        action: 能力名（query/create/update/report/knowledge）
        user_info: 用户信息（保留参数，兼容历史调用点，当前不再依赖它做权限判定）

    Returns:
        PolicyDecision: ALLOW / REQUIRE_CONFIRMATION
    """
    if action == "update":
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
