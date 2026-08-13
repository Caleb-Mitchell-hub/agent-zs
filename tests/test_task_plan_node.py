"""task_plan 节点 + 意图分类测试（monkeypatch mock 基础设施）"""
import pytest
from app.orchestrator import langgraph_flow
from app.orchestrator.langgraph_flow import route_by_intent, task_plan_node


class FakeSessionMemory:
    async def add_message(self, *a, **k): pass
    async def get_messages(self, *a, **k): return []
    async def get_context(self, *a, **k): return {}
    async def update_context(self, *a, **k): pass


class FakeTaskMemory:
    async def save_task(self, *a, **k): return True


class FakeMemoryExtractor:
    async def should_extract(self, m): return False


class FakeAuditLogger:
    async def log(self, *a, **k): pass


@pytest.fixture(autouse=True)
def mock_infra(monkeypatch):
    monkeypatch.setattr(langgraph_flow, "session_memory", FakeSessionMemory())
    monkeypatch.setattr(langgraph_flow, "task_memory", FakeTaskMemory())
    monkeypatch.setattr(langgraph_flow, "memory_extractor", FakeMemoryExtractor())
    monkeypatch.setattr(langgraph_flow, "audit_logger", FakeAuditLogger())
    langgraph_flow._compiled_graph = None


def test_route_by_intent_task_plan():
    assert route_by_intent({"intent": "task_plan"}) == "task_plan_node"


@pytest.mark.asyncio
async def test_task_plan_node_today(monkeypatch):
    async def fake_workday_sets(user_id, year):
        return set(), set(), set()
    monkeypatch.setattr("app.orchestrator.langgraph_flow.get_workday_sets", fake_workday_sets)
    result = await task_plan_node({
        "user_input": "今日任务：完成库存盘点",
        "user_id": 1,
    })
    assert result["result"]["status"] == "ok"
    assert result["result"]["preview"] is True
    assert result["result"]["data"][0]["title"] == "完成库存盘点"
    assert result["agent_name"] == "task_planner"


@pytest.mark.asyncio
async def test_classify_intent_task_plan(monkeypatch):
    """规则引擎识别「本月任务」为 task_plan 意图"""
    from app.orchestrator.planner import planner
    assert await planner.classify_intent("本月任务：梳理采购流程") == "task_plan"
