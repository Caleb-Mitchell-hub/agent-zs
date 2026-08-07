"""工具执行器测试

验证：ToolExecutor 强制执行二次确认、超时、规则化重试。
"""

import asyncio

import pytest

from app.tools.registry import ToolRegistry, ToolExecutor


@pytest.fixture
def registry():
    return ToolRegistry()


@pytest.fixture
def executor(registry):
    return ToolExecutor(registry=registry)


class TestToolExecutor:
    @pytest.mark.asyncio
    async def test_need_confirm_blocks_execution(self, registry, executor):
        """测试需要确认的工具未确认时不执行"""
        async def risky():
            raise AssertionError("不应执行")

        registry.register("risky_tool", risky, need_confirm=True)
        result = await executor.execute_tool("risky_tool", confirmed=False)
        assert result["status"] == "waiting_confirm"

    @pytest.mark.asyncio
    async def test_need_confirm_executes_after_confirmed(self, registry, executor):
        """测试确认后执行成功"""
        async def risky():
            return {"status": "ok", "result": "done"}

        registry.register("risky_tool", risky, need_confirm=True)
        result = await executor.execute_tool("risky_tool", confirmed=True)
        assert result["status"] == "ok"

    @pytest.mark.asyncio
    async def test_timeout_returns_error(self, registry, executor):
        """测试超时被拦截"""
        async def slow():
            await asyncio.sleep(5)

        registry.register("slow_tool", slow, timeout=1, retry_count=0)
        result = await executor.execute_tool("slow_tool")
        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_retryable_error_retries(self, registry, executor):
        """测试网络类错误按 retry_count 重试"""
        calls = []

        async def flaky():
            calls.append(1)
            if len(calls) < 3:
                raise OSError("网络错误")
            return {"status": "ok"}

        registry.register("flaky_tool", flaky, retry_count=3)
        result = await executor.execute_tool("flaky_tool")
        assert result["status"] == "ok"
        assert len(calls) == 3

    @pytest.mark.asyncio
    async def test_value_error_no_retry(self, registry, executor):
        """测试参数错误不重试直接报错"""
        calls = []

        async def bad():
            calls.append(1)
            raise ValueError("参数错误")

        registry.register("bad_tool", bad, retry_count=3)
        result = await executor.execute_tool("bad_tool")
        assert result["status"] == "error"
        assert len(calls) == 1

    @pytest.mark.asyncio
    async def test_unregistered_tool(self, executor):
        """测试未注册工具返回错误"""
        result = await executor.execute_tool("not_exist")
        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_dict_result_passthrough(self, registry, executor):
        """测试 dict 结果透传"""
        async def tool():
            return {"status": "ok", "data": [1, 2, 3]}

        registry.register("ok_tool", tool)
        result = await executor.execute_tool("ok_tool")
        assert result == {"status": "ok", "data": [1, 2, 3]}


class TestToolRegistry:
    def test_risk_level_default_medium(self, registry):
        registry.register("t", lambda: None)
        assert registry.get_metadata("t").risk_level == "medium"

    def test_risk_level_custom(self, registry):
        registry.register("t", lambda: None, risk_level="high")
        assert registry.get_metadata("t").risk_level == "high"
