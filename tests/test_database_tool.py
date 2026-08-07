"""Database Tool 单元测试

覆盖：
- _build_context_hint：上一轮查询参考构建
- _build_history：对话历史格式化（角色标签）
"""

import pytest
from app.tools.database_tool import DatabaseTool


# ============================================================
# _build_context_hint：上一轮查询参考
# ============================================================

def test_context_hint_empty_context():
    """空上下文 → 提示无参考"""
    tool = DatabaseTool()
    hint = tool._build_context_hint({})
    assert "无上一轮查询参考" in hint


def test_context_hint_with_query_only():
    """仅有 last_query，无 SQL/结果"""
    tool = DatabaseTool()
    hint = tool._build_context_hint({"last_query": "汇总上海仓库3的数量"})
    assert "汇总上海仓库3的数量" in hint
    # 没有 SQL 行（只有追问引导语中含 SQL 字样，但不应该有"上一轮执行的 SQL"行）
    assert "上一轮执行的 SQL:" not in hint


def test_context_hint_with_query_and_sql():
    """有 last_query + last_sql"""
    tool = DatabaseTool()
    context = {
        "last_query": "汇总上海仓库3的数量",
        "last_sql": "SELECT w.warehouse_name, SUM(i.quantity) AS 总数量 FROM inventory i JOIN warehouse w ON i.warehouse_id = w.id WHERE w.warehouse_name LIKE '%上海仓库3%' GROUP BY w.warehouse_name",
    }
    hint = tool._build_context_hint(context)
    assert "汇总上海仓库3的数量" in hint
    assert "上一轮执行的 SQL:" in hint
    assert "上海仓库3" in hint


def test_context_hint_with_full_context():
    """完整上下文：query + sql + last_result（含数据）"""
    tool = DatabaseTool()
    context = {
        "last_query": "汇总上海仓库3的数量",
        "last_sql": "SELECT w.warehouse_name, SUM(i.quantity) AS total FROM inventory i JOIN warehouse w ON i.warehouse_id = w.id WHERE w.warehouse_name LIKE '%上海仓库3%' GROUP BY w.warehouse_name",
        "last_result": {
            "data": [{"仓库": "上海仓库3", "总数量": 91}],
            "sql": "SELECT w.warehouse_name, SUM(i.quantity) AS total FROM inventory i JOIN warehouse w ON i.warehouse_id = w.id WHERE w.warehouse_name LIKE '%上海仓库3%' GROUP BY w.warehouse_name",
            "count": 1,
        },
    }
    hint = tool._build_context_hint(context)
    assert "汇总上海仓库3的数量" in hint
    assert "上一轮执行的 SQL:" in hint
    assert "上一轮结果: 1 条" in hint
    assert "字段包括:" in hint
    assert "仓库" in hint
    assert "总数量" in hint
    # 追问引导语
    assert "沿用上一轮 SQL 的查询结构" in hint
    assert "X呢？" in hint


def test_context_hint_with_last_result_sql_fallback():
    """last_sql 在顶层缺失时，从 last_result.sql 获取"""
    tool = DatabaseTool()
    context = {
        "last_query": "查询库存",
        "last_result": {
            "sql": "SELECT * FROM inventory",
            "data": [],
            "count": 0,
        },
    }
    hint = tool._build_context_hint(context)
    assert "上一轮执行的 SQL:" in hint
    assert "SELECT * FROM inventory" in hint
    assert "上一轮结果: 0 条" in hint


def test_context_hint_empty_result():
    """上一轮查询结果为空"""
    tool = DatabaseTool()
    context = {
        "last_query": "查询xyz",
        "last_sql": "SELECT * FROM warehouse WHERE warehouse_name = 'xyz'",
        "last_result": {"data": [], "count": 0},
    }
    hint = tool._build_context_hint(context)
    assert "上一轮执行的 SQL:" in hint
    assert "上一轮结果: 0 条" in hint


# ============================================================
# _build_history：对话历史角色标签
# ============================================================

def test_build_history_user_role():
    """用户消息使用"用户"标签"""
    tool = DatabaseTool()
    messages = [{"role": "user", "content": "查询库存"}]
    history = tool._build_history(messages)
    assert history == "用户: 查询库存"


def test_build_history_assistant_role():
    """AI助手消息使用AI助手标签，不使用系统或assistant标签"""
    tool = DatabaseTool()
    messages = [{"role": "assistant", "content": "查到了 3 条记录"}]
    history = tool._build_history(messages)
    assert "AI助手:" in history
    assert "系统:" not in history


def test_build_history_mixed_roles():
    """混合消息：user + assistant"""
    tool = DatabaseTool()
    messages = [
        {"role": "user", "content": "汇总上海仓库3的数量"},
        {"role": "assistant", "content": "上海仓库3 共 91 件商品"},
        {"role": "user", "content": "上海仓库5呢？"},
    ]
    history = tool._build_history(messages)
    lines = history.split("\n")
    assert lines[0] == "用户: 汇总上海仓库3的数量"
    assert lines[1] == "AI助手: 上海仓库3 共 91 件商品"
    assert lines[2] == "用户: 上海仓库5呢？"


def test_build_history_empty():
    """空消息列表"""
    tool = DatabaseTool()
    history = tool._build_history([])
    assert "无历史" in history


def test_build_history_unknown_role():
    """未知角色 → "系统" 兜底"""
    tool = DatabaseTool()
    messages = [{"role": "system", "content": "internal message"}]
    history = tool._build_history(messages)
    assert history == "系统: internal message"


# ============================================================
# 集成：context_hint 对追问 SQL 生成的帮助
# ============================================================

def test_context_hint_contains_follow_up_guidance():
    """context_hint 必须包含追问引导语，告诉 LLM 如何理解"X呢？"模式"""
    tool = DatabaseTool()
    hint = tool._build_context_hint({"last_query": "汇总上海仓库3的数量"})
    assert "沿用上一轮 SQL 的查询结构" in hint
    assert "替换" in hint
