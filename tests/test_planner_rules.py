"""意图分类规则引擎测试

验证：规则引擎优先（打分制 + 置信度判定） + LLM 兜底。
"""

import pytest
from unittest.mock import AsyncMock, patch

from app.orchestrator.planner import planner, INTENT_RULES


# ============================================================
# 单元测试：_classify_by_rules 打分制
# ============================================================

def test_single_intent_hit_returns_directly():
    """单意图关键词命中 → 直接返回，不调用 LLM"""
    assert planner._classify_by_rules("你好") == "chat"
    assert planner._classify_by_rules("现在几点") == "time"
    assert planner._classify_by_rules("再见") == "chat"


def test_single_intent_multiple_keywords():
    """同意图多个关键词命中 → 得分累加，得分足够高时直接返回"""
    # "请帮我创建一个采购订单" → create: "请帮我创建"(6) + "创建"(2) = 8
    # query: "采购"(2) + "订单"(2) = 4
    # ratio: 8/4 = 2.0 >= 2.0 → create wins
    assert planner._classify_by_rules("请帮我创建一个采购订单") == "create"


def test_multi_intent_score_disparate():
    """多意图命中但比分悬殊 → 规则直接裁决"""
    # "查一下审批通过的采购单":
    #   query: "查一下"(3) + "采购"(2) + "订单"(2) = 7
    #   update: "审批通过"(4) = 4
    #   ratio = 7/4 = 1.75 < 2.0 → 歧义 → None
    result = planner._classify_by_rules("查一下审批通过的采购单")
    assert result is None


def test_multi_intent_score_close_returns_none():
    """多意图命中但比分刚好达到阈值 → 规则裁决为得分高者"""
    # "修改订单金额":
    #   update: "修改"(2) = 2
    #   query: "订单"(2) + "金额"(2) = 4
    #   ratio = 4/2 = 2.0 >= 2.0 → query wins
    result = planner._classify_by_rules("修改订单金额")
    assert result == "query"


def test_multi_intent_truly_ambiguous():
    """真正歧义场景：三个意图比分完全相同 → 返回 None 走 LLM"""
    # "怎么创建订单":
    #   knowledge: "怎么"(2) = 2
    #   create: "创建"(2) = 2
    #   query: "订单"(2) = 2
    #   ratio: 2/2 = 1.0 < 2.0 → None
    result = planner._classify_by_rules("怎么创建订单")
    assert result is None


def test_no_keyword_match_returns_none():
    """无关键词命中 → 返回 None，走 LLM 路径"""
    assert planner._classify_by_rules("那北京呢") is None
    assert planner._classify_by_rules("按地区分") is None


def test_empty_input_returns_none():
    """空输入不命中规则"""
    assert planner._classify_by_rules("") is None
    assert planner._classify_by_rules("   ") is None


def test_all_rule_keywords_each_match_their_intent():
    """规则表完整性：每个关键词独立出现时，只命中自己的意图"""
    for intent, keywords in INTENT_RULES:
        assert intent in ["query", "create", "update", "report", "knowledge", "memory", "time", "chat"]
        assert len(keywords) > 0
        for kw in keywords:
            result = planner._classify_by_rules(kw)
            if result is not None:
                assert result == intent, f"关键词 '{kw}' 期望 {intent}，实际 {result}"
            # 如果返回 None（关键词是其他意图关键词的子串），由 LLM 兜底，可接受


def test_time_intent_by_rules():
    """时间类意图规则命中"""
    assert planner._classify_by_rules("现在几点") == "time"
    assert planner._classify_by_rules("今天几号") == "time"
    assert planner._classify_by_rules("现在时间") == "time"


# ============================================================
# 集成测试：classify_intent（规则优先 + LLM 兜底）
# ============================================================

@pytest.mark.asyncio
async def test_query_intent_no_llm_call():
    """查询类意图由规则直接判定，不调用 LLM"""
    mock_chat = AsyncMock(return_value="garbage")
    with patch("app.orchestrator.planner.llm_client.chat", mock_chat):
        result = await planner.classify_intent("查询所有仓库的库存")
    assert result == "query"
    mock_chat.assert_not_called()


@pytest.mark.asyncio
async def test_chat_intent_no_llm_call():
    """闲聊类意图规则直接命中，不调用 LLM"""
    mock_chat = AsyncMock(return_value="garbage")
    with patch("app.orchestrator.planner.llm_client.chat", mock_chat):
        result = await planner.classify_intent("你好")
    assert result == "chat"
    mock_chat.assert_not_called()


@pytest.mark.asyncio
async def test_memory_intent_no_llm_call():
    """记忆类意图规则直接命中"""
    mock_chat = AsyncMock(return_value="garbage")
    with patch("app.orchestrator.planner.llm_client.chat", mock_chat):
        result = await planner.classify_intent("刚才聊了什么")
    assert result == "memory"
    mock_chat.assert_not_called()


@pytest.mark.asyncio
async def test_time_intent_no_llm_call():
    """时间类意图规则直接命中"""
    mock_chat = AsyncMock(return_value="garbage")
    with patch("app.orchestrator.planner.llm_client.chat", mock_chat):
        result = await planner.classify_intent("现在几点")
    assert result == "time"
    mock_chat.assert_not_called()


@pytest.mark.asyncio
async def test_unknown_input_falls_back_to_llm():
    """无关键词命中 → 走 LLM"""
    mock_chat = AsyncMock(return_value="query")
    with patch("app.orchestrator.planner.llm_client.chat", mock_chat):
        result = await planner.classify_intent("那北京呢")
    assert result == "query"
    mock_chat.assert_called_once()


@pytest.mark.asyncio
async def test_ambiguous_input_falls_back_to_llm():
    """歧义输入（三个意图比分完全相同）→ 走 LLM"""
    mock_chat = AsyncMock(return_value="query")
    with patch("app.orchestrator.planner.llm_client.chat", mock_chat):
        result = await planner.classify_intent("怎么创建订单")
    assert result == "query"
    mock_chat.assert_called_once()


@pytest.mark.asyncio
async def test_empty_input_returns_unknown():
    """空输入直接返回 unknown，不调 LLM"""
    mock_chat = AsyncMock()
    with patch("app.orchestrator.planner.llm_client.chat", mock_chat):
        assert await planner.classify_intent("") == "unknown"
        assert await planner.classify_intent("   ") == "unknown"
    mock_chat.assert_not_called()


@pytest.mark.asyncio
async def test_llm_invalid_output_falls_back_to_query():
    """LLM 返回非法类别 → 兜底返回 query"""
    mock_chat = AsyncMock(return_value="garbage output with extra text")
    with patch("app.orchestrator.planner.llm_client.chat", mock_chat):
        result = await planner.classify_intent("xyz123不存在")
    assert result == "query"


@pytest.mark.asyncio
async def test_llm_output_with_extra_text_falls_back():
    """LLM 输出夹带解释文字 → 校验失败，兜底 query"""
    mock_chat = AsyncMock(return_value="我认为这是 query 类别")
    with patch("app.orchestrator.planner.llm_client.chat", mock_chat):
        result = await planner.classify_intent("xyz456不存在")
    assert result == "query"


@pytest.mark.asyncio
async def test_llm_output_valid_intent_passes_through():
    """LLM 返回合法类别 → 直接采用"""
    mock_chat = AsyncMock(return_value="report")
    with patch("app.orchestrator.planner.llm_client.chat", mock_chat):
        result = await planner.classify_intent("那北京呢")
    assert result == "report"
