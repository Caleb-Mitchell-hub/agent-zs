"""多轮追问一致性路由测试

验证：追问复用/重新查询判断完全由确定性代码决定，零 LLM。
"""

import pytest

from app.tools.follow_up_router import (
    is_follow_up,
    should_reuse_result,
    compose_reuse_reply,
)


@pytest.fixture
def context_with_result():
    """构造含上次查询结果的会话上下文"""
    return {
        "last_query": "查询上海仓库的库存",
        "last_result": {
            "data": [
                {"仓库": "上海仓", "库存数量": 100},
                {"仓库": "上海仓", "库存数量": 200},
            ],
            "sql": "SELECT ... WHERE w.address LIKE '%上海%'",
            "count": 2,
        },
    }


class TestIsFollowUp:
    def test_no_previous_result_not_follow_up(self):
        assert is_follow_up("查询北京库存", {}) is False

    def test_short_query_is_follow_up(self, context_with_result):
        assert is_follow_up("北京呢？", context_with_result) is True

    def test_refer_back_marker_is_follow_up(self, context_with_result):
        assert is_follow_up("刚才那些仓库总共有多少", context_with_result) is True

    def test_new_long_query_not_reused(self, context_with_result):
        """测试全新长查询即使有上次结果也必须重新查询（不应复用）"""
        assert should_reuse_result("我想查询所有供应商的采购订单明细和金额", context_with_result) is False


class TestShouldReuseResult:
    def test_new_city_forces_requery(self, context_with_result):
        """测试"北京呢？"触发重新查询（换了地名）"""
        assert should_reuse_result("北京呢？", context_with_result) is False

    def test_refer_back_reuses(self, context_with_result):
        """测试引用上次结果时复用"""
        assert should_reuse_result("刚才那批仓库总共有多少？", context_with_result) is True

    def test_lookup_modifier_reuses(self, context_with_result):
        """测试纯汇总查看复用"""
        assert should_reuse_result("总共多少？", context_with_result) is True

    def test_time_change_forces_requery(self, context_with_result):
        """测试换时间范围触发重新查询"""
        assert should_reuse_result("上月的呢？", context_with_result) is False


class TestComposeReuseReply:
    def test_reuse_reply_contains_data(self, context_with_result):
        reply = compose_reuse_reply("刚才那批总共有多少？", context_with_result)
        assert reply["status"] == "ok"
        assert reply["reused"] is True
        assert len(reply["data"]) == 2
        assert "2 条" in reply["message"]

    def test_reuse_reply_empty_result(self):
        reply = compose_reuse_reply("总共多少？", {
            "last_query": "查询上海库存",
            "last_result": {"data": [], "sql": None, "count": 0},
        })
        assert reply["status"] == "ok"
        assert "为空" in reply["message"]
