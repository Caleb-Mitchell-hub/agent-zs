"""计划校验器测试（纯函数，零外部依赖）

验证：action 白名单 / 依赖引用存在 / 自依赖 / 环检测 / 传参引用 / 拓扑分层。
"""

from app.orchestrator.plan_schema import Plan, PlanStep
from app.orchestrator.plan_validator import validate_plan, topological_layers, _has_cycle


def make_plan(steps: list[dict]) -> Plan:
    """构造 Plan 对象"""
    return Plan(goal="测试目标", steps=[PlanStep(**s) for s in steps])


# ============================================================
# validate_plan 基础校验
# ============================================================

def test_valid_plan():
    """合法计划：通过校验"""
    plan = make_plan([
        {"id": "s1", "action": "query", "params": {"question": "上海库存"}},
        {"id": "s2", "action": "create", "params": {}, "after": ["s1"]},
    ])
    assert validate_plan(plan)["valid"] is True


def test_invalid_action():
    """非法 action 被拒绝"""
    plan = make_plan([{"id": "s1", "action": "delete"}])
    check = validate_plan(plan)
    assert check["valid"] is False
    assert any("action" in e for e in check["errors"])


def test_duplicate_step_id():
    """重复步骤 id 被拒绝"""
    plan = make_plan([
        {"id": "s1", "action": "query"},
        {"id": "s1", "action": "query"},
    ])
    check = validate_plan(plan)
    assert check["valid"] is False
    assert any("重复" in e for e in check["errors"])


def test_self_dependency():
    """自依赖被拒绝"""
    plan = make_plan([{"id": "s1", "action": "query", "after": ["s1"]}])
    check = validate_plan(plan)
    assert check["valid"] is False
    assert any("自身" in e for e in check["errors"])


def test_missing_dependency():
    """依赖不存在的步骤被拒绝"""
    plan = make_plan([{"id": "s1", "action": "query", "after": ["s99"]}])
    check = validate_plan(plan)
    assert check["valid"] is False
    assert any("不存在" in e for e in check["errors"])


def test_cycle_detection():
    """循环依赖被检测出来"""
    plan = make_plan([
        {"id": "s1", "action": "query", "after": ["s2"]},
        {"id": "s2", "action": "query", "after": ["s1"]},
    ])
    check = validate_plan(plan)
    assert check["valid"] is False
    assert any("循环" in e for e in check["errors"])


def test_ref_to_missing_step():
    """传参引用不存在的步骤被拒绝"""
    plan = make_plan([
        {"id": "s1", "action": "query", "params": {"question": "$s99.output"}},
    ])
    check = validate_plan(plan)
    assert check["valid"] is False


def test_valid_ref():
    """合法的传参引用通过校验"""
    plan = make_plan([
        {"id": "s1", "action": "query"},
        {"id": "s2", "action": "query", "params": {"question": "$s1.output.count"}, "after": ["s1"]},
    ])
    assert validate_plan(plan)["valid"] is True


# ============================================================
# 环检测 / 拓扑分层
# ============================================================

def test_has_cycle_false_for_dag():
    """无环 DAG：_has_cycle 返回 False"""
    plan = make_plan([
        {"id": "s1", "action": "query"},
        {"id": "s2", "action": "query"},
        {"id": "s3", "action": "create", "after": ["s1", "s2"]},
    ])
    assert _has_cycle(plan) is False


def test_topological_layers_parallel():
    """无依赖的步骤分到同一层（可并行）"""
    plan = make_plan([
        {"id": "s1", "action": "query"},
        {"id": "s2", "action": "query"},
        {"id": "s3", "action": "create", "after": ["s1", "s2"]},
    ])
    layers = topological_layers(plan)
    assert layers[0] == ["s1", "s2"]
    assert layers[1] == ["s3"]


def test_topological_layers_chain():
    """链式依赖逐层串行"""
    plan = make_plan([
        {"id": "s1", "action": "query"},
        {"id": "s2", "action": "query", "after": ["s1"]},
        {"id": "s3", "action": "create", "after": ["s2"]},
    ])
    assert topological_layers(plan) == [["s1"], ["s2"], ["s3"]]
