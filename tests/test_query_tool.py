"""查询工具测试"""

import pytest
from app.tools.query_tool import _validate_sql


def test_validate_sql_rejects_non_select():
    """测试拒绝非 SELECT 语句"""
    with pytest.raises(ValueError, match="只允许 SELECT"):
        _validate_sql("INSERT INTO users VALUES (1, 'test')")


def test_validate_sql_rejects_delete():
    """测试拒绝 DELETE 语句"""
    with pytest.raises(ValueError):
        _validate_sql("DELETE FROM users WHERE id = 1")


def test_validate_sql_rejects_drop():
    """测试拒绝 DROP 语句"""
    with pytest.raises(ValueError):
        _validate_sql("DROP TABLE users")


def test_validate_sql_rejects_update():
    """测试拒绝 UPDATE 语句"""
    with pytest.raises(ValueError):
        _validate_sql("UPDATE users SET name = 'test'")


def test_validate_sql_accepts_select():
    """测试接受 SELECT 语句"""
    # 不应该抛出异常
    _validate_sql("SELECT * FROM users WHERE id = 1")


def test_validate_sql_accepts_select_with_join():
    """测试接受带 JOIN 的 SELECT"""
    _validate_sql("""
        SELECT u.name, o.total
        FROM users u
        JOIN orders o ON u.id = o.user_id
    """)


def test_validate_sql_rejects_create():
    """测试拒绝 CREATE 语句"""
    with pytest.raises(ValueError):
        _validate_sql("CREATE TABLE test (id INT)")
