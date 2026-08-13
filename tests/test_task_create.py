"""task_create 意图 + 节点测试（对话创建任务，区分「创建单据」vs「创建任务」）"""
import pytest

from app.orchestrator.planner import planner, extract_task_title
from app.orchestrator import langgraph_flow
from app.orchestrator.langgraph_flow import route_by_intent, task_create_node


# ── extract_task_title：确定性标题提取 ──

def test_extract_task_title_create():
    assert extract_task_title("创建任务：明天开会") == "明天开会"
    assert extract_task_title("创建任务 明天开会") == "明天开会"
    assert extract_task_title("新增待办 交季度报表") == "交季度报表"
    assert extract_task_title("新建任务：整理会议纪要") == "整理会议纪要"
    assert extract_task_title("添加一个任务 买牛奶") == "买牛奶"


def test_extract_task_title_remind():
    assert extract_task_title("提醒我下午提交周报") == "下午提交周报"
    assert extract_task_title("提醒我明天开会") == "明天开会"
    assert extract_task_title("设置提醒 下午3点打电话") == "下午3点打电话"


def test_extract_task_title_empty_falls_back():
    # 只输入「创建任务」无标题 → 回退原文，由调用方兜底
    assert extract_task_title("创建任务") == "创建任务"


# ── 意图分类：区分创建单据（create）vs 创建任务（task_create）──

def test_classify_create_document_not_task():
    # 业务单据 → create（ERP 建单）
    assert planner._classify_by_rules("创建采购订单") == "create"
    assert planner._classify_by_rules("新增一个销售订单") == "create"
    assert planner._classify_by_rules("新建入库单") == "create"


def test_classify_task_create_intent():
    # 任务/待办/提醒 → task_create
    assert planner._classify_by_rules("创建任务") == "task_create"
    assert planner._classify_by_rules("提醒我明天开会") == "task_create"
    assert planner._classify_by_rules("新增待办 交周报") == "task_create"
    assert planner._classify_by_rules("设置提醒 下午打电话") == "task_create"


# ── 路由 ──

def test_route_by_intent_task_create():
    assert route_by_intent({"intent": "task_create"}) == "task_create_node"


# ── task_create_node：落库节点 ──

@pytest.mark.asyncio
async def test_task_create_node(monkeypatch):
    created = {}

    async def fake_create_task(user_id, title):
        created["user_id"] = user_id
        created["title"] = title
        return {"task_id": 1}

    monkeypatch.setattr(langgraph_flow, "create_task", fake_create_task)
    result = await task_create_node({"user_input": "创建任务：明天开会", "user_id": 1})
    assert result["result"]["status"] == "ok"
    assert result["result"]["task_created"] is True
    assert result["agent_name"] == "task_creator"
    assert created == {"user_id": 1, "title": "明天开会"}
