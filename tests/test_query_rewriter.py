"""查询改写节点测试

验证：省略式追问（换人名/换条件）在进入 NL→SQL 前被补全为自包含查询。
"""

import pytest

from app.orchestrator.query_rewriter import (
    needs_query_rewrite,
    rewrite_if_needed,
)


@pytest.fixture
def followup_context():
    """模拟上一轮「查询我的销售订单」后的会话上下文"""
    return {
        "last_query": "查询我的销售订单",
        "last_sql": "SELECT order_no FROM sales_order WHERE deleted = 0 AND created_by = 42",
        "last_result": {
            "data": [{"订单编号": "SO001"}],
            "sql": "SELECT order_no FROM sales_order WHERE deleted = 0 AND created_by = 42",
            "count": 1,
        },
    }


class TestNeedsQueryRewrite:
    def test_no_previous_query_returns_false(self):
        assert needs_query_rewrite("查询王横的", {}) is False

    def test_empty_input_returns_false(self, followup_context):
        assert needs_query_rewrite("", followup_context) is False

    def test_omitted_object_needs_rewrite(self, followup_context):
        """换人名且省略业务对象 → 需要改写"""
        assert needs_query_rewrite("查询王横的", followup_context) is True

    def test_self_contained_query_skips_rewrite(self, followup_context):
        """已含业务对象词 → 无需改写"""
        assert needs_query_rewrite("查询所有销售订单", followup_context) is False
        assert needs_query_rewrite("查询北京仓库的库存", followup_context) is False

    def test_change_condition_needs_rewrite(self, followup_context):
        """换条件追问（无业务对象词）→ 需要改写"""
        assert needs_query_rewrite("北京呢", followup_context) is True
        assert needs_query_rewrite("换成李四", followup_context) is True


class TestRewriteIfNeeded:
    @pytest.mark.asyncio
    async def test_skip_when_not_needed(self, followup_context):
        """自包含查询原样返回，不调 LLM"""
        result = await rewrite_if_needed("查询所有销售订单", [], followup_context)
        assert result == "查询所有销售订单"

    @pytest.mark.asyncio
    async def test_rewrite_omitted_object(self, followup_context, monkeypatch):
        """省略追问被改写为完整查询"""
        from app.agent.llm_client import llm_client

        async def fake_chat(prompt):
            assert "查询我的销售订单" in prompt
            assert "created_by" in prompt  # 上一轮 SQL 注入，供继承人员维度
            return "查询王横创建的销售订单"

        monkeypatch.setattr(llm_client, "chat", fake_chat)

        result = await rewrite_if_needed("查询王横的", [], followup_context)
        assert result == "查询王横创建的销售订单"

    @pytest.mark.asyncio
    async def test_rewrite_llm_failure_falls_back(self, followup_context, monkeypatch):
        """LLM 调用失败时沿用原始输入（不阻塞查询）"""
        from app.agent.llm_client import llm_client

        async def fake_chat(prompt):
            raise RuntimeError("llm down")

        monkeypatch.setattr(llm_client, "chat", fake_chat)

        result = await rewrite_if_needed("查询王横的", [], followup_context)
        assert result == "查询王横的"
