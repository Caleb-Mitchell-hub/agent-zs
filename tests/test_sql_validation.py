"""SQL 确定性列名校验测试

验证：执行前用 schema 结构校验列名，拦截 LLM 幻觉的列名，不依赖 LLM 纠错。
"""

import pytest

from app.tools.database_tool import DatabaseTool

# 模拟 schema 结构：{表名: {列名集合}}
FAKE_STRUCTURE = {
    "warehouse": {"id", "warehouse_name", "address", "tenant_id"},
    "inventory": {"id", "warehouse_id", "sku_id", "quantity", "locked_quantity", "available_quantity"},
    "purchase_order": {"id", "order_no", "supplier_name", "order_date", "total_amount", "status"},
    "sales_order": {"id", "order_no", "customer_name", "order_date", "total_amount", "status"},
}


@pytest.fixture
def db_tool():
    return DatabaseTool()


@pytest.mark.asyncio
async def test_valid_sql_passes(db_tool):
    """测试合法 SQL 通过校验"""
    sql = "SELECT w.warehouse_name, i.quantity FROM inventory i JOIN warehouse w ON i.warehouse_id = w.id"
    bad = await db_tool._validate_sql_against_schema(sql, FAKE_STRUCTURE)
    assert bad == []


@pytest.mark.asyncio
async def test_nonexistent_column_detected(db_tool):
    """测试幻觉列名被拦截（ps.unit 场景）"""
    sql = "SELECT ps.unit, ps.quantity FROM inventory ps"
    bad = await db_tool._validate_sql_against_schema(sql, FAKE_STRUCTURE)
    assert "unit" in bad


@pytest.mark.asyncio
async def test_nonexistent_table_column_detected(db_tool):
    """测试裸列名不在任何表时被拦截"""
    sql = "SELECT some_fake_column FROM inventory"
    bad = await db_tool._validate_sql_against_schema(sql, FAKE_STRUCTURE)
    assert "some_fake_column" in bad


@pytest.mark.asyncio
async def test_aggregate_functions_ignored(db_tool):
    """测试聚合函数/关键字不被误报"""
    sql = "SELECT COUNT(*), SUM(total_amount) FROM purchase_order WHERE status = 'APPROVED'"
    bad = await db_tool._validate_sql_against_schema(sql, FAKE_STRUCTURE)
    assert "COUNT" not in bad
    assert "total_amount" not in bad


@pytest.mark.asyncio
async def test_string_literals_ignored(db_tool):
    """测试字符串字面量不参与列名校验"""
    sql = "SELECT warehouse_name FROM warehouse WHERE address LIKE '%北京%'"
    bad = await db_tool._validate_sql_against_schema(sql, FAKE_STRUCTURE)
    assert bad == []


@pytest.mark.asyncio
async def test_wildcard_ignored(db_tool):
    """测试 * 和 alias.* 不被当作列名"""
    sql = "SELECT w.*, i.quantity FROM inventory i JOIN warehouse w ON i.warehouse_id = w.id"
    bad = await db_tool._validate_sql_against_schema(sql, FAKE_STRUCTURE)
    assert bad == []
