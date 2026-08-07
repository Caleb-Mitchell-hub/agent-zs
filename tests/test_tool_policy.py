"""工具策略接线测试"""

import pytest

from app.tools.registry import ToolRegistry, ToolExecutor


@pytest.fixture
def registry():
    r = ToolRegistry()
    r.register("query_tool", lambda: {"status": "ok"}, risk_level="medium", need_confirm=False)
    return r


class TestApplyPolicy:
    def test_apply_policy_changes_fields(self, registry):
        registry.apply_policy("query_tool", enabled=False, risk_level="high", timeout=60, retry_count=5)
        meta = registry.get_metadata("query_tool")
        assert meta.enabled is False
        assert meta.risk_level == "high"
        assert meta.timeout == 60
        assert meta.retry_count == 5

    def test_apply_policy_partial(self, registry):
        """只改部分字段，其余保持默认"""
        registry.apply_policy("query_tool", risk_level="low")
        meta = registry.get_metadata("query_tool")
        assert meta.risk_level == "low"
        assert meta.timeout == 30  # 未改，保持默认
        assert meta.enabled is True

    def test_apply_policy_unknown_tool_no_error(self, registry):
        registry.apply_policy("not_exist", enabled=False)
        assert registry.get_metadata("not_exist") is None


class TestDisabledTool:
    @pytest.mark.asyncio
    async def test_disabled_tool_blocked(self, registry):
        executor = ToolExecutor(registry=registry)
        registry.apply_policy("query_tool", enabled=False)
        result = await executor.execute_tool("query_tool")
        assert result["status"] == "error"
        assert result["error_code"] == "TOOL_DISABLED"

    @pytest.mark.asyncio
    async def test_enabled_tool_executes(self, registry):
        executor = ToolExecutor(registry=registry)
        result = await executor.execute_tool("query_tool")
        assert result["status"] == "ok"


class TestListToolsFull:
    def test_list_tools_full_has_all_fields(self, registry):
        tools = registry.list_tools_full()
        assert len(tools) == 1
        t = tools[0]
        assert t["name"] == "query_tool"
        assert t["risk_level"] == "medium"
        assert t["enabled"] is True
        assert "timeout" in t
        assert "retry_count" in t
        assert "need_confirm" in t
        assert "permission_level" in t
