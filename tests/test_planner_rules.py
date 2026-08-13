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
        assert intent in ["query", "create", "update", "report", "knowledge", "memory", "time", "weather", "chat"]
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


def test_weather_intent_by_rules():
    """天气类意图规则命中"""
    assert planner._classify_by_rules("今天天气怎么样") == "weather"
    assert planner._classify_by_rules("北京明天会下雨吗") == "weather"
    # "温度"(2)+"多少度"(3)=5 vs query"多少"(2)，5/2=2.5 >= 2.0 → weather
    assert planner._classify_by_rules("温度多少度") == "weather"


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
async def test_weather_intent_no_llm_call():
    """天气类意图规则直接命中"""
    mock_chat = AsyncMock(return_value="garbage")
    with patch("app.orchestrator.planner.llm_client.chat", mock_chat):
        result = await planner.classify_intent("今天天气怎么样")
    assert result == "weather"
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


# ============================================================
# _is_data_follow_up：上下文感知数据追问检测
# ============================================================

def make_data_context(last_query="汇总上海仓库3的数量", data=None, count=2):
    """构建测试用的 last_result 上下文"""
    if data is None:
        data = [
            {"仓库": "上海仓库3", "SKU ID": 3, "库存数量": 57},
            {"仓库": "上海仓库3", "SKU ID": 6, "库存数量": 34},
        ]
    return {
        "last_query": last_query,
        "last_result": {
            "data": data,
            "sql": "SELECT w.warehouse_name, i.sku_id, i.quantity FROM inventory i JOIN warehouse w ON i.warehouse_id = w.id WHERE w.warehouse_name LIKE '%上海仓库3%'",
            "count": len(data),
        },
    }


def test_no_data_context_not_follow_up():
    """无 last_result → 不是数据追问"""
    assert planner._is_data_follow_up("什么意思只有2个仓库", {}) is False
    assert planner._is_data_follow_up("为什么这么少", {"last_result": None}) is False


def test_empty_result_not_follow_up():
    """last_result 数据为空 → 不是有效数据追问"""
    ctx = make_data_context(data=[])
    assert planner._is_data_follow_up("只有这些吗", ctx) is False


def test_question_patterns_trigger_data_follow_up():
    """质疑/追问模式词 → 命中数据追问"""
    ctx = make_data_context()
    patterns = [
        "什么意思只有2个仓库",
        "为什么只有这些",
        "怎么只有2条",
        "就这些吗",
        "只有上海仓库3吗",
        "不对吧",
        "确定吗",
        "有没有遗漏",
        "还有别的仓库吗",
        "其他的仓库呢",
        "全部的仓库有哪些",
    ]
    for text in patterns:
        assert planner._is_data_follow_up(text, ctx), f"应该命中数据追问: {text}"


def test_result_value_in_user_input_triggers_follow_up():
    """用户输入中包含上一轮结果的具体值 → 命中"""
    ctx = make_data_context()
    # "上海仓库3" 在上轮结果中
    assert planner._is_data_follow_up("上海仓库3还有其他SKU吗", ctx) is True
    # "57" 在上轮结果中
    assert planner._is_data_follow_up("为什么57这么少", ctx) is True


def test_value_not_in_result_no_trigger():
    """用户输入中不包含结果值 → 不命中"""
    ctx = make_data_context()
    # "北京仓库" 不在上轮结果中
    assert planner._is_data_follow_up("北京仓库有哪些", ctx) is False


def test_short_follow_up_with_data_context():
    """极短追问（≤6字）+ 有上轮数据 → 命中"""
    ctx = make_data_context()
    assert planner._is_data_follow_up("为什么", ctx) is True
    assert planner._is_data_follow_up("还有呢", ctx) is True
    assert planner._is_data_follow_up("就这？", ctx) is True


def test_medium_length_new_query_not_follow_up():
    """7字以上的新查询（即使含问号）不应被短输入规则误判"""
    ctx = make_data_context()
    # "北京仓库有哪些" 是7字新查询，不含质疑模式，不匹配上轮结果值
    assert planner._is_data_follow_up("北京仓库有哪些", ctx) is False


def test_long_non_data_message_not_follow_up():
    """长输入且不含质疑模式、不含量化值 → 不命中"""
    ctx = make_data_context()
    assert planner._is_data_follow_up("你好今天天气不错我们聊点别的吧", ctx) is False


def test_very_short_greeting_not_follow_up():
    """极短闲聊信号（你好等）不应被短输入规则误判"""
    ctx = make_data_context()
    assert planner._is_data_follow_up("你好", ctx) is False
    assert planner._is_data_follow_up("谢谢", ctx) is False


def test_unrelated_short_input_not_follow_up():
    """无关短输入（非追问、非聊天）不应被误判为数据追问

    回归测试：曾因 C 分支用「排除法」判定，导致"你是？""哈哈哈""安排行程"
    等任何 ≤6 字的无关输入都被判为数据追问，进而复用上次库存查询结果。
    """
    ctx = make_data_context()
    assert planner._is_data_follow_up("你是？", ctx) is False
    assert planner._is_data_follow_up("哈哈哈", ctx) is False
    assert planner._is_data_follow_up("安排行程", ctx) is False


# ============================================================
# classify_intent 上下文感知集成测试
# ============================================================

@pytest.mark.asyncio
async def test_context_aware_routes_to_query_before_llm():
    """有数据上下文 + 规则零命中 → 上下文感知判为 query，不调 LLM"""
    ctx = make_data_context()
    mock_chat = AsyncMock(return_value="chat")
    with patch("app.orchestrator.planner.llm_client.chat", mock_chat):
        result = await planner.classify_intent("什么意思只有2个仓库", context=ctx)
    assert result == "query"
    mock_chat.assert_not_called()  # 不应该走到 LLM


@pytest.mark.asyncio
async def test_context_aware_no_data_context_still_falls_back_to_llm():
    """无数据上下文 + 规则零命中 → 仍然走 LLM"""
    mock_chat = AsyncMock(return_value="chat")
    with patch("app.orchestrator.planner.llm_client.chat", mock_chat):
        result = await planner.classify_intent("那北京呢")
    assert result == "chat"
    mock_chat.assert_called_once()


@pytest.mark.asyncio
async def test_context_aware_rule_hit_still_wins():
    """规则命中时仍然直接返回，不走上下文感知"""
    ctx = make_data_context()
    mock_chat = AsyncMock(return_value="garbage")
    with patch("app.orchestrator.planner.llm_client.chat", mock_chat):
        # "你好" 规则引擎命中 chat，应直接返回 chat，不走到 _is_data_follow_up
        result = await planner.classify_intent("你好", context=ctx)
    assert result == "chat"
    mock_chat.assert_not_called()
