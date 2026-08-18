"""策略引擎（权限码驱动）测试（纯函数，零外部依赖）

验证：has_permission 权限码校验 / evaluate_policy 风险控制 / 权限码映射表 / 数据范围打包。

权限判定由后端 ERP 返回的权限码（perm_code）驱动，不再使用自定义角色集合。
"""

from app.policy.engine import (
    has_permission,
    evaluate_policy,
    PolicyDecision,
    build_user_permissions,
    TABLE_VIEW_PERMISSION,
    DOC_TYPE_ADD_PERMISSION,
)


# ============================================================
# has_permission（后端权限码驱动）
# ============================================================

def test_has_permission_super_admin():
    """超级管理员恒放行（perm_codes 为 None）"""
    assert has_permission(None, True, "SALES_ORDER_VIEW") is True


def test_has_permission_has_code():
    """拥有权限码 → 放行"""
    assert has_permission(["SALES_ORDER_VIEW"], False, "SALES_ORDER_VIEW") is True


def test_has_permission_missing_code():
    """缺少权限码 → 拒绝"""
    assert has_permission(["INVENTORY_VIEW"], False, "SALES_ORDER_VIEW") is False


def test_has_permission_none_denied():
    """非 admin 且权限码为 None（未加载）→ 安全默认拒绝"""
    assert has_permission(None, False, "SALES_ORDER_VIEW") is False


def test_has_permission_empty_list_denied():
    """非 admin 且权限码为空列表 → 拒绝"""
    assert has_permission([], False, "SALES_ORDER_VIEW") is False


# ============================================================
# evaluate_policy（风险控制层，非权限判定）
# ============================================================

def test_update_requires_confirmation():
    """update 是高风险，即使超级管理员也需人工确认"""
    assert evaluate_policy("update", {"is_super_admin": True}) == PolicyDecision.REQUIRE_CONFIRMATION


def test_create_no_longer_role_gated():
    """创建不再由自定义角色集合判定，权限下沉到 doc_type 级 ADD 权限码"""
    assert evaluate_policy("create", {"is_super_admin": False, "roles": ["viewer"]}) == PolicyDecision.ALLOW


def test_read_actions_allow():
    """读操作默认放行，权限下沉到表级 VIEW 权限码校验"""
    assert evaluate_policy("query") == PolicyDecision.ALLOW
    assert evaluate_policy("report") == PolicyDecision.ALLOW
    assert evaluate_policy("knowledge") == PolicyDecision.ALLOW


# ============================================================
# 权限码映射表（后端 ERP 权限码命名：{业务对象}_{操作}）
# ============================================================

def test_table_view_permission_mapping():
    """表名 → VIEW 权限码映射正确"""
    assert TABLE_VIEW_PERMISSION["sales_order"] == "SALES_ORDER_VIEW"
    assert TABLE_VIEW_PERMISSION["inventory"] == "INVENTORY_VIEW"
    assert TABLE_VIEW_PERMISSION["warehouse"] == "WAREHOUSE_VIEW"
    # 明细表跟随主单
    assert TABLE_VIEW_PERMISSION["purchase_order_item"] == "PURCHASE_ORDER_VIEW"


def test_doc_type_add_permission_mapping():
    """doc_type → ADD 权限码映射正确"""
    assert DOC_TYPE_ADD_PERMISSION["sales_order"] == "SALES_ORDER_ADD"
    assert DOC_TYPE_ADD_PERMISSION["purchase_order"] == "PURCHASE_ORDER_ADD"
    assert DOC_TYPE_ADD_PERMISSION["expense_reimbursement"] == "EXPENSE_ADD"


# ============================================================
# build_user_permissions（ABAC 数据范围）
# ============================================================

def test_build_user_permissions():
    """按字段打包数据范围权限"""
    info = {"warehouse_ids": [1, 2], "region_ids": [3]}
    perms = build_user_permissions(info)
    assert perms["warehouse_ids"] == [1, 2]
    assert perms["region_ids"] == [3]
    assert perms["customer_ids"] == []
    assert perms["product_ids"] == []


def test_build_user_permissions_none():
    """user_info 为空时返回空列表"""
    perms = build_user_permissions(None)
    assert perms["warehouse_ids"] == []
    assert perms["region_ids"] == []
    assert perms["customer_ids"] == []
    assert perms["product_ids"] == []
