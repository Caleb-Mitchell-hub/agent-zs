"""策略引擎（RBAC/ABAC）测试（纯函数，零外部依赖）

验证：超级管理员放行 / 写权限拒绝 / 高风险强制确认 / 数据范围打包。
"""

from app.policy.engine import evaluate_policy, PolicyDecision, build_user_permissions


# ============================================================
# evaluate_policy（RBAC + 风险）
# ============================================================

def test_super_admin_allow_query():
    """超级管理员查询直接放行"""
    assert evaluate_policy("query", {"is_super_admin": True}) == PolicyDecision.ALLOW


def test_query_allowed_default():
    """查询类操作无 user_info 时默认放行（读操作低风险）"""
    assert evaluate_policy("query", None) == PolicyDecision.ALLOW
    assert evaluate_policy("report", {}) == PolicyDecision.ALLOW
    assert evaluate_policy("knowledge", {}) == PolicyDecision.ALLOW


def test_write_denied_for_non_writer():
    """无写权限角色创建单据被拒绝"""
    decision = evaluate_policy("create", {"is_super_admin": False, "roles": ["viewer"]})
    assert decision == PolicyDecision.DENY


def test_write_allowed_for_admin_role():
    """admin 角色创建单据放行"""
    assert evaluate_policy("create", {"roles": ["admin"]}) == PolicyDecision.ALLOW


def test_write_allowed_for_super_admin():
    """超级管理员即使无 roles 也放行"""
    assert evaluate_policy("create", {"is_super_admin": True, "roles": []}) == PolicyDecision.ALLOW


def test_update_requires_confirmation():
    """update 是高风险，即使超级管理员也需人工确认"""
    assert evaluate_policy("update", {"is_super_admin": True}) == PolicyDecision.REQUIRE_CONFIRMATION


def test_update_denied_takes_precedence():
    """无写权限 + update：先拒绝，不会到确认阶段"""
    assert evaluate_policy("update", {"roles": ["viewer"]}) == PolicyDecision.DENY


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
