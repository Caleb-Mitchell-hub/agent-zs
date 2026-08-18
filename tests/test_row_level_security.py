"""行级数据安全测试（B1 空权限拒绝 + B2 SQL 确定性拦截）

验证 database_tool 的两层数据范围防护：
- B1：非 admin 用户无任何数据范围 → 拒绝查询（不再误判为「无限制」）
- B2：用户有 warehouse 范围，SQL 涉及 warehouse 表但缺少过滤 → 拦截

纯函数测试，不连数据库。
"""

import pytest

from app.tools.database_tool import DatabaseTool


@pytest.fixture
def tool():
    return DatabaseTool()


# ============================================================
# B1：_check_data_scope（空权限拒绝）
# ============================================================

def test_scope_super_admin_unlimited(tool):
    """超级管理员不受限"""
    assert tool._check_data_scope({"is_super_admin": True, "warehouse_ids": []}) is None


def test_scope_none_skipped(tool):
    """未提供权限信息（内部/测试路径）不拦截"""
    assert tool._check_data_scope(None) is None


def test_scope_empty_denied(tool):
    """非 admin 且无任何数据范围 → 拒绝（核心越权漏洞修复）"""
    err = tool._check_data_scope({
        "is_super_admin": False,
        "warehouse_ids": [], "region_ids": [], "customer_ids": [], "product_ids": [],
    })
    assert err is not None
    assert "无数据访问权限" in err


def test_scope_with_warehouse_allowed(tool):
    """有仓库范围 → 放行"""
    assert tool._check_data_scope({
        "is_super_admin": False,
        "warehouse_ids": [1], "region_ids": [], "customer_ids": [], "product_ids": [],
    }) is None


def test_scope_with_region_only_allowed(tool):
    """只有区域范围（无仓库）也算有范围 → 放行"""
    assert tool._check_data_scope({
        "is_super_admin": False,
        "warehouse_ids": [], "region_ids": [3], "customer_ids": [], "product_ids": [],
    }) is None


# ============================================================
# B2：_enforce_row_level_filter（SQL 确定性拦截）
# ============================================================

def test_filter_super_admin_skipped(tool):
    """admin 无限制，不做 SQL 拦截"""
    assert tool._enforce_row_level_filter(
        "SELECT * FROM warehouse", {"is_super_admin": True}) is None


def test_filter_no_warehouse_scope_skipped(tool):
    """无 warehouse 范围 → 跳过 warehouse 维度"""
    assert tool._enforce_row_level_filter(
        "SELECT * FROM warehouse", {"is_super_admin": False, "warehouse_ids": []}) is None


def test_filter_no_warehouse_table_skipped(tool):
    """查询不涉及 warehouse 表 → 无需仓库过滤"""
    assert tool._enforce_row_level_filter(
        "SELECT * FROM customer WHERE id = 1",
        {"is_super_admin": False, "warehouse_ids": [1]}) is None


def test_filter_warehouse_without_where_blocked(tool):
    """涉及 warehouse 表但无 WHERE → 拦截"""
    err = tool._enforce_row_level_filter(
        "SELECT * FROM warehouse", {"is_super_admin": False, "warehouse_ids": [1]})
    assert err is not None
    assert "越权查询" in err


def test_filter_warehouse_alias_id_filter_allowed(tool):
    """WHERE 含 warehouse 别名 id 过滤 → 放行"""
    sql = ("SELECT i.sku_id, i.quantity FROM inventory i "
           "JOIN warehouse w ON i.warehouse_id = w.id WHERE w.id IN (1, 2)")
    assert tool._enforce_row_level_filter(
        sql, {"is_super_admin": False, "warehouse_ids": [1, 2]}) is None


def test_filter_warehouse_by_name_allowed(tool):
    """WHERE 含仓库名过滤 → 放行"""
    sql = "SELECT w.warehouse_name FROM warehouse w WHERE w.warehouse_name LIKE '%北京%'"
    assert tool._enforce_row_level_filter(
        sql, {"is_super_admin": False, "warehouse_ids": [1]}) is None


def test_filter_warehouse_where_without_scope_blocked(tool):
    """涉及 warehouse 表，WHERE 有条件但未限定仓库 → 拦截"""
    sql = ("SELECT i.sku_id FROM inventory i "
           "JOIN warehouse w ON i.warehouse_id = w.id WHERE i.quantity > 0")
    err = tool._enforce_row_level_filter(
        sql, {"is_super_admin": False, "warehouse_ids": [1]})
    assert err is not None


def test_filter_warehouse_join_on_not_counted(tool):
    """JOIN ON 里的 warehouse_id 不算 WHERE 过滤，仍拦截"""
    sql = "SELECT i.sku_id FROM inventory i JOIN warehouse w ON i.warehouse_id = w.id"
    err = tool._enforce_row_level_filter(
        sql, {"is_super_admin": False, "warehouse_ids": [1]})
    assert err is not None


# ============================================================
# 表级权限校验：_enforce_view_permission（后端权限码驱动）
# ============================================================

def test_view_perm_super_admin_allowed(tool):
    """超级管理员不受表级权限限制"""
    assert tool._enforce_view_permission(
        "SELECT * FROM sales_order", {"is_super_admin": True}) is None


def test_view_perm_none_skipped(tool):
    """未提供权限信息（内部/测试路径）不拦截"""
    assert tool._enforce_view_permission("SELECT * FROM sales_order", None) is None


def test_view_perm_has_code_allowed(tool):
    """拥有对应 VIEW 权限码 → 放行"""
    assert tool._enforce_view_permission(
        "SELECT * FROM sales_order",
        {"is_super_admin": False, "perm_codes": ["SALES_ORDER_VIEW"]}) is None


def test_view_perm_missing_code_denied(tool):
    """缺少对应 VIEW 权限码 → 拒绝"""
    err = tool._enforce_view_permission(
        "SELECT * FROM sales_order",
        {"is_super_admin": False, "perm_codes": ["INVENTORY_VIEW"]})
    assert err is not None
    assert "SALES_ORDER_VIEW" in err


def test_view_perm_unmapped_table_allowed(tool):
    """未映射的表（如 supplier 等菜单级业务）不做表级校验"""
    assert tool._enforce_view_permission(
        "SELECT * FROM supplier",
        {"is_super_admin": False, "perm_codes": []}) is None


def test_view_perm_missing_perm_codes_denied(tool):
    """非 admin 且 perm_codes 为 None（未加载权限）→ 拒绝"""
    err = tool._enforce_view_permission(
        "SELECT * FROM sales_order",
        {"is_super_admin": False, "perm_codes": None})
    assert err is not None


def test_view_perm_join_table_checked(tool):
    """JOIN 涉及的表也会校验 VIEW 权限码"""
    err = tool._enforce_view_permission(
        "SELECT i.sku_id FROM inventory i JOIN warehouse w ON i.warehouse_id = w.id",
        {"is_super_admin": False, "perm_codes": ["INVENTORY_VIEW"]})
    assert err is not None
    assert "WAREHOUSE_VIEW" in err
