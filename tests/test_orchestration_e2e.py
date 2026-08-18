"""多任务编排端到端集成测试

验证完整链路：复杂请求 → query_understanding 判复杂 → planning → validate
→ execute_plan（DAG 分层并行）→ aggregate。

不依赖真实 Redis/MySQL/LLM，通过 monkeypatch 替换外部依赖。
"""

import pytest
from unittest.mock import AsyncMock

from app.orchestrator import langgraph_flow
from app.orchestrator import task_executor as task_executor_mod
from app.orchestrator.plan_schema import Plan, PlanStep


class FakeSessionMemory:
    async def add_message(self, *a, **k):
        pass
    async def get_messages(self, *a, **k):
        return []
    async def get_context(self, *a, **k):
        return {}
    async def update_context(self, *a, **k):
        pass


class FakeTaskMemory:
    async def save_task(self, *a, **k):
        return True


class FakeMemoryExtractor:
    async def should_extract(self, messages):
        return False


class FakeAuditLogger:
    async def log(self, *a, **k):
        pass


@pytest.fixture(autouse=True)
def mock_infra(monkeypatch):
    """替换外部基础设施依赖"""
    monkeypatch.setattr(langgraph_flow, "session_memory", FakeSessionMemory())
    monkeypatch.setattr(langgraph_flow, "task_memory", FakeTaskMemory())
    monkeypatch.setattr(langgraph_flow, "memory_extractor", FakeMemoryExtractor())
    monkeypatch.setattr(langgraph_flow, "audit_logger", FakeAuditLogger())
    langgraph_flow._compiled_graph = None


@pytest.fixture
def graph():
    return langgraph_flow.build_graph()


@pytest.mark.asyncio
async def test_complex_request_planning_path(graph, monkeypatch):
    """复杂多任务请求走规划路径，3 个步骤全部执行并聚合"""
    plan = Plan(goal="查库存并生成补货单", steps=[
        PlanStep(id="s1", action="query", params={"question": "上海库存"}),
        PlanStep(id="s2", action="query", params={"question": "采购在途"}),
        PlanStep(id="s3", action="create", params={"doc_type": "purchase_order"}, after=["s1", "s2"]),
    ])

    # mock 规划器：直接返回 Plan，不调 LLM
    monkeypatch.setattr(langgraph_flow.planner, "plan_task", AsyncMock(return_value=plan))

    # mock 结果聚合
    import app.orchestrator.aggregator as agg_mod
    monkeypatch.setattr(agg_mod.aggregator, "aggregate", AsyncMock(return_value="已查库存、在途并生成补货单"))

    # mock 执行 Agent（task_executor 内部实例化）
    executed = []

    class FakeDataAgent:
        async def execute(self, user_input, messages, context, session_id, user_id, tenant_id, user_permissions=None):
            executed.append(("query", user_input))
            return {"status": "ok", "data": [], "sql": None, "message": f"查询: {user_input}"}

    class FakeWriteAgent:
        async def execute(self, user_input, messages, context, session_id, user_id, tenant_id):
            executed.append(("create", user_input))
            return {"status": "ok", "data": None, "sql": None, "message": f"创建: {user_input}"}

    monkeypatch.setattr(task_executor_mod, "DataAgent", FakeDataAgent)
    monkeypatch.setattr(task_executor_mod, "WriteAgent", FakeWriteAgent)

    result = await graph.ainvoke({
        "user_input": "查上海库存，顺便查采购在途，然后生成补货单",
        "session_id": "test-sess",
        "user_id": 1,
        "tenant_id": 1,
        "intent": "query",  # 前端直达，跳过分类 LLM
        "user_info": {"is_super_admin": True, "roles": ["admin"]},
    })

    assert result["result"]["status"] == "ok"
    assert result["result"]["message"] == "已查库存、在途并生成补货单"
    assert result["agent_name"] == "planner"
    # 3 个步骤都被执行（2 query + 1 create）
    assert len(executed) == 3
    assert {a for a, _ in executed} == {"query", "create"}


@pytest.mark.asyncio
async def test_simple_request_stays_single_intent(graph, monkeypatch):
    """简单请求仍走原单意图路由，不触发规划（零回归）"""
    called = []

    class FakeDataAgent:
        async def execute(self, user_input, messages, context, session_id, user_id, tenant_id, user_permissions=None):
            called.append(user_input)
            return {"status": "ok", "data": [{"仓库": "北京仓"}], "sql": "SELECT 1", "message": "1 条记录"}

    monkeypatch.setattr(task_executor_mod, "DataAgent", FakeDataAgent)
    # 注意：简单请求走 data_node，data_node 内部用自己的 DataAgent 实例
    monkeypatch.setattr(langgraph_flow, "DataAgent", FakeDataAgent)

    result = await graph.ainvoke({
        "user_input": "查询所有仓库",
        "session_id": "test-sess",
        "user_id": 1,
        "tenant_id": 1,
        "intent": "query",
    })

    assert result["result"]["status"] == "ok"
    assert result["agent_name"] == "data_agent"
