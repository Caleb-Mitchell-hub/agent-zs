"""复杂度路由（Query Understanding）测试

验证：多句/并列/条件/跨域/多意图命中 → 需规划；
单意图 → 简单；无信号 → LLM 兜底。
"""

import pytest
from unittest.mock import AsyncMock, patch

from app.orchestrator.query_understanding import query_understanding


# ============================================================
# _rules_detect（确定性规则）
# ============================================================

def test_multi_sentence_requires_planning():
    """多句输入 → 需规划"""
    assert query_understanding._rules_detect("查上海库存？顺便查采购在途") is True
    assert query_understanding._rules_detect("库存有多少；在途呢") is True


def test_coordination_signal_requires_planning():
    """并列/顺序信号 → 需规划"""
    assert query_understanding._rules_detect("查库存然后生成补货单") is True
    assert query_understanding._rules_detect("查库存顺便查在途") is True


def test_condition_signal_requires_planning():
    """条件/分支信号 → 需规划"""
    assert query_understanding._rules_detect("如果库存不足就创建补货单") is True


def test_cross_domain_requires_planning():
    """查询信号 + 写操作信号并存 → 需规划"""
    assert query_understanding._rules_detect("查询库存并创建采购订单") is True


def test_single_intent_not_planning():
    """单意图单句 → 简单请求"""
    assert query_understanding._rules_detect("查询上海仓库库存") is False
    assert query_understanding._rules_detect("创建一个采购订单") is False


def test_empty_input_not_planning():
    """空输入 → 简单（不规划）"""
    assert query_understanding._rules_detect("") is False
    assert query_understanding._rules_detect("   ") is False


def test_no_keyword_returns_none():
    """无关键词命中（可能是指代/追问）→ 返回 None 交 LLM"""
    assert query_understanding._rules_detect("那北京呢") is None


# ============================================================
# analyze（规则优先 + LLM 兜底）
# ============================================================

@pytest.mark.asyncio
async def test_analyze_rule_hit_no_llm():
    """规则命中复杂 → 不调 LLM"""
    mock_chat = AsyncMock(return_value="garbage")
    with patch("app.orchestrator.query_understanding.llm_client.chat", mock_chat):
        result = await query_understanding.analyze("查库存顺便查在途")
    assert result["requires_planning"] is True
    mock_chat.assert_not_called()


@pytest.mark.asyncio
async def test_analyze_simple_no_llm():
    """规则判定简单 → 不调 LLM"""
    mock_chat = AsyncMock(return_value="garbage")
    with patch("app.orchestrator.query_understanding.llm_client.chat", mock_chat):
        result = await query_understanding.analyze("查询上海仓库库存")
    assert result["requires_planning"] is False
    mock_chat.assert_not_called()


@pytest.mark.asyncio
async def test_analyze_fallback_to_llm():
    """规则无法判定 → 调 LLM 兜底"""
    mock_chat = AsyncMock(return_value='{"requires_planning": true, "intents": ["query", "create"]}')
    with patch("app.orchestrator.query_understanding.llm_client.chat", mock_chat):
        result = await query_understanding.analyze("那北京呢")
    assert result["requires_planning"] is True
    assert result["intents"] == ["query", "create"]
    mock_chat.assert_called_once()


@pytest.mark.asyncio
async def test_analyze_llm_error_defaults_simple():
    """LLM 判定异常 → 降级为简单请求（不阻断）"""
    mock_chat = AsyncMock(side_effect=Exception("boom"))
    with patch("app.orchestrator.query_understanding.llm_client.chat", mock_chat):
        result = await query_understanding.analyze("那北京呢")
    assert result["requires_planning"] is False
    assert result["intents"] == []
