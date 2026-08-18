"""Plan IR 规划测试

验证：plan_from_dict 容错解析 / plan_task 输出多步骤计划（mock LLM）。
"""

import pytest
from unittest.mock import AsyncMock, patch

from app.orchestrator.plan_schema import plan_from_dict, Plan, PlanStep
from app.orchestrator.planner import planner


# ============================================================
# plan_from_dict（容错解析）
# ============================================================

def test_parse_valid_plan():
    data = {
        "goal": "查库存并生成补货单",
        "steps": [
            {"id": "s1", "action": "query", "params": {"question": "上海库存"}, "after": []},
            {"id": "s2", "action": "create", "params": {"doc_type": "purchase_order"}, "after": ["s1"]},
        ],
    }
    plan = plan_from_dict(data)
    assert isinstance(plan, Plan)
    assert plan.goal == "查库存并生成补货单"
    assert len(plan.steps) == 2
    assert plan.steps[1].after == ["s1"]


def test_parse_tolerates_depends_on_alias():
    """兼容 depends_on 字段名"""
    data = {
        "goal": "g",
        "steps": [
            {"id": "s1", "action": "query", "depends_on": []},
        ],
    }
    plan = plan_from_dict(data)
    assert plan.steps[0].after == []


def test_parse_action_lowercases():
    """action 统一转小写"""
    data = {"goal": "g", "steps": [{"id": "s1", "action": "Query"}]}
    assert plan_from_dict(data).steps[0].action == "query"


def test_parse_missing_steps_raises():
    """缺少 steps 字段抛 ValueError"""
    with pytest.raises(ValueError):
        plan_from_dict({"goal": "g"})


def test_parse_non_dict_raises():
    """非字典输入抛 ValueError"""
    with pytest.raises(ValueError):
        plan_from_dict("not a dict")


def test_parse_empty_steps_raises():
    """空 steps 抛 ValueError"""
    with pytest.raises(ValueError):
        plan_from_dict({"goal": "g", "steps": []})


# ============================================================
# plan_task（LLM 输出 → Plan）
# ============================================================

@pytest.mark.asyncio
async def test_plan_task_multi_step():
    """LLM 输出多步骤计划 → 正确解析为 Plan"""
    llm_json = (
        '{"goal": "查库存并生成补货单", "steps": ['
        '{"id": "s1", "action": "query", "params": {"question": "上海库存"}, "after": []},'
        '{"id": "s2", "action": "query", "params": {"question": "采购在途"}, "after": []},'
        '{"id": "s3", "action": "create", "params": {"doc_type": "purchase_order"}, "after": ["s1", "s2"]}'
        ']}'
    )
    mock_chat = AsyncMock(return_value=llm_json)
    with patch("app.orchestrator.planner.llm_client.chat", mock_chat):
        plan = await planner.plan_task("查上海库存顺便查采购在途然后生成补货单")
    assert isinstance(plan, Plan)
    assert len(plan.steps) == 3
    assert plan.steps[2].after == ["s1", "s2"]


@pytest.mark.asyncio
async def test_plan_task_strips_code_block():
    """LLM 输出夹带 markdown 代码块 → 仍能解析"""
    llm_raw = '```json\n{"goal": "g", "steps": [{"id": "s1", "action": "query"}]}\n```'
    mock_chat = AsyncMock(return_value=llm_raw)
    with patch("app.orchestrator.planner.llm_client.chat", mock_chat):
        plan = await planner.plan_task("查询库存")
    assert len(plan.steps) == 1
    assert plan.steps[0].action == "query"


@pytest.mark.asyncio
async def test_plan_task_invalid_json_raises():
    """LLM 未返回 JSON → 抛 ValueError"""
    mock_chat = AsyncMock(return_value="抱歉我无法规划")
    with patch("app.orchestrator.planner.llm_client.chat", mock_chat):
        with pytest.raises(ValueError):
            await planner.plan_task("随便问点什么")
