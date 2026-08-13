"""LangGraph 编排流程

将 Orchestrator 的线性 if/elif 流程重写为 LangGraph 图结构。
图节点严格区分「LLM节点」与「确定性代码节点」：

- 确定性节点（零 LLM 成本）：安全检查、消息存储、意图分类（规则）、路由、历史保存、记忆抽取
- LLM 节点：data_node（NL→SQL）、conversation_node（对话/闲聊）、knowledge_node（回答生成）、
  report_node（模板未命中兜底）、write_node（参数抽取）

设计文档 §2.2「确定性优先」：路由/风控/重试判断一律用确定性代码，LLM 只负责
自然语言理解与生成。
"""

import logging
from datetime import datetime
from typing import TypedDict, Any

from langgraph.graph import StateGraph, START, END

from app.security.prompt_guard import prompt_guard
from app.security.circuit_breaker import circuit_breaker_manager
from app.security.audit import audit_logger
from app.memory import session_memory
from app.memory.task_memory import task_memory
from app.memory.extractor import memory_extractor
from app.orchestrator.planner import planner
from app.tools.follow_up_router import should_reuse_result, compose_reuse_reply
from app.tools.time_tool import TimeTool
from app.tools.weather_tool import WeatherTool
from app.agents.data_agent import DataAgent
from app.agents.write_agent import WriteAgent
from app.agents.knowledge_agent import KnowledgeAgent
from app.agents.report_agent import ReportAgent
from app.tasks.planner import parse_plan_input, split_today, split_month, split_year
from app.tasks.service import get_workday_sets

logger = logging.getLogger(__name__)


class AgentState(TypedDict, total=False):
    """LangGraph 全链路状态"""
    user_input: str
    session_id: str
    user_id: int
    tenant_id: int
    intent: str          # 前端直达意图（query/create/...）或规则引擎结果
    messages: list[dict]
    context: dict
    result: dict
    task_id: str
    trace_id: str
    agent_name: str
    error: str
    progress_callback: Any  # 进度回调（可选，流式输出）


async def _emit_progress(state: AgentState, message: str) -> None:
    """发送进度事件（如果配置了进度回调）"""
    callback = state.get("progress_callback")
    if callback is None:
        return
    try:
        await callback(message)
    except Exception as e:
        logger.warning(f"进度事件发送失败: {e}")


def _with_progress(message: str, node):
    """给图节点包一层进度事件发送，不修改节点本身逻辑"""
    async def wrapped(state: AgentState) -> dict:
        await _emit_progress(state, message)
        return await node(state)
    return wrapped


# ─────────────────────────── 确定性节点 ───────────────────────────

async def security_check(state: AgentState) -> dict:
    """安全检查（确定性）：Prompt 注入防护 + 输入清洗"""
    user_input = state["user_input"]
    safety_check = prompt_guard.check_input(user_input)
    if not safety_check["safe"]:
        logger.warning(f"检测到注入威胁: {safety_check['threats']}")
        await audit_logger.log(
            "unsafe_input", str(state.get("user_id", "")),
            str(state.get("tenant_id", "")), {"input": user_input},
            risk_level="high", trace_id=state.get("trace_id"),
        )
        return {
            "result": {"status": "error", "message": "输入包含不安全内容", "error_code": "UNSAFE_INPUT"},
            "error": "unsafe_input",
        }
    return {"user_input": prompt_guard.sanitize_input(user_input)}


async def save_user_message(state: AgentState) -> dict:
    """保存用户消息到 Redis（确定性）"""
    await session_memory.add_message(state["session_id"], "user", state["user_input"])
    return {}


async def classify_intent(state: AgentState) -> dict:
    """意图分类（确定性规则优先，未命中 LLM 兜底）"""
    # 前端快捷入口直接携带意图，跳过分类（设计文档 §5.1）
    if state.get("intent"):
        logger.info(f"前端直达意图: {state['intent']} (输入: {state['user_input'][:50]})")
        return {}

    intent = await planner.classify_intent(
        state["user_input"], state.get("messages"), state.get("context"),
    )
    return {"intent": intent}


async def save_history(state: AgentState) -> dict:
    """保存任务历史 + 助手消息（确定性）"""
    task_id = state.get("task_id") or f"task-{datetime.now().strftime('%H%M%S%f')}"
    result = state.get("result", {})
    await task_memory.save_task(
        task_id=task_id,
        session_id=state["session_id"],
        user_id=state.get("user_id", 0),
        tenant_id=state.get("tenant_id", 1),
        task_type=state.get("intent", "unknown"),
        agent_name=state.get("agent_name", ""),
        input_data={"user_input": state["user_input"], "context": state.get("context", {})},
        output_data=result,
        status="completed" if result.get("status") == "ok" else "failed",
    )
    await session_memory.add_message(state["session_id"], "assistant", result.get("message", ""))
    return {"task_id": task_id}


async def memory_extract(state: AgentState) -> dict:
    """记忆抽取（确定性正则，每10条触发）"""
    try:
        messages = state.get("messages") or []
        if await memory_extractor.should_extract(messages):
            conversation = "\n".join([f"{m['role']}: {m['content']}" for m in messages[-10:]])
            await memory_extractor.extract_and_save(
                conversation, str(state.get("user_id", "")),
                str(state.get("tenant_id", "")), state["session_id"],
            )
    except Exception as e:
        logger.warning(f"记忆抽取失败: {e}")
    return {}


# ─────────────────────────── LLM 节点 ───────────────────────────

async def data_node(state: AgentState) -> dict:
    """数据查询节点（LLM NL→SQL + 确定性校验）

    多轮追问一致性（设计文档 §5.3）：
    - 追问可复用上次结果时，直接基于 last_result 组织回复，不重新查询
    - 涉及新查询条件时，强制重新触发真实查询，禁止凭记忆推测
    """
    user_input = state["user_input"]
    context = state.get("context") or {}

    # 追问复用判断（确定性规则，零 LLM）
    if should_reuse_result(user_input, context):
        logger.info(f"追问复用上次查询结果: {user_input[:50]}")
        result = compose_reuse_reply(user_input, context)
        # 如果复用结果有效（非 error 且有数据），直接返回
        if result.get("status") == "ok" and result.get("data"):
            return {"result": result, "agent_name": "data_agent"}
        # 否则 fall through 到正常查询
        logger.info(f"复用结果无效（{result.get('message')}），改为重新查询")

    # 正常查询
    agent = DataAgent()
    result = await agent.execute(
        user_input, state.get("messages") or [], context,
        state["session_id"], state.get("user_id", 0), state.get("tenant_id", 1),
        state.get("user_permissions"),
    )

    # 查询成功时，把完整结构化结果写入 context（供后续追问复用）
    if result.get("status") == "ok":
        try:
            await session_memory.update_context(state["session_id"], {
                "last_result": {
                    "data": result.get("data") or [],
                    "sql": result.get("sql"),
                    "count": len(result.get("data") or []),
                },
                "last_query": user_input,
            })
        except Exception as e:
            logger.warning(f"保存追问上下文失败: {e}")

    return {"result": result, "agent_name": "data_agent"}


async def knowledge_node(state: AgentState) -> dict:
    """知识检索节点（确定性检索 + LLM 回答生成）"""
    agent = KnowledgeAgent()
    result = await agent.execute(
        state["user_input"], state.get("messages") or [], state.get("context") or {},
        state["session_id"], state.get("user_id", 0), state.get("tenant_id", 1),
    )
    return {"result": result, "agent_name": "knowledge_agent"}


async def report_node(state: AgentState) -> dict:
    """报表节点（模板优先，未命中 LLM 兜底）"""
    agent = ReportAgent()
    result = await agent.execute(
        state["user_input"], state.get("messages") or [], state.get("context") or {},
        state["session_id"], state.get("user_id", 0), state.get("tenant_id", 1),
    )
    return {"result": result, "agent_name": "report_agent"}


async def write_node(state: AgentState) -> dict:
    """写操作节点（LLM 参数抽取 + ERP 调用）"""
    agent = WriteAgent()
    result = await agent.execute(
        state["user_input"], state.get("messages") or [], state.get("context") or {},
        state["session_id"], state.get("user_id", 0), state.get("tenant_id", 1),
    )
    return {"result": result, "agent_name": "write_agent"}


async def conversation_node(state: AgentState) -> dict:
    """对话/闲聊/记忆节点（LLM 生成）

    上下文感知：即使意图分类误判为 chat，本节点也会参考上一轮查询结果，
    避免"刚查到数据，追问却完全失忆"的情况。
    """
    user_input = state["user_input"]
    messages = state.get("messages") or []
    recent = messages[-20:] if len(messages) > 20 else messages
    history_text = "\n".join([
        f"{'用户' if m['role'] == 'user' else 'AI'}: {m['content'][:500]}"
        for m in recent
    ])

    # 构建上一轮数据查询上下文（如果存在）
    context = state.get("context") or {}
    last_result = context.get("last_result")
    data_context_text = ""
    if last_result and isinstance(last_result, dict):
        last_query = context.get("last_query", "")
        data = last_result.get("data") or []
        sql = last_result.get("sql", "")
        data_context_text = f"\n## 上一轮数据查询上下文\n- 上一轮问题: {last_query}\n- SQL: {sql}\n- 结果({len(data)}条): {str(data[:5])[:1000]}"

    # 加载用户长期记忆（偏好、习惯、事实等）
    user_memory_text = ""
    try:
        from app.memory.user_memory import user_memory
        user_id = state.get("user_id", 0)
        if user_id:
            prefs = await user_memory.get_user_preferences(user_id)
            if prefs:
                # 提取记忆内容（排除 recent_queries 和 default_filters）
                memory_items = []
                for k, v in prefs.items():
                    if k in ("recent_queries", "default_filters"):
                        continue
                    if isinstance(v, dict):
                        content = v.get("content", "")
                        mtype = v.get("memory_type", "")
                        if content:
                            memory_items.append(f"- [{mtype}] {content}")
                    elif isinstance(v, str):
                        memory_items.append(f"- {v}")
                if memory_items:
                    user_memory_text = "\n## 用户长期记忆\n" + "\n".join(memory_items[-10:])
    except Exception:
        pass

    from app.agent.llm_client import llm_client
    prompt = f"""你是一个企业 AI 助手，具有对话记忆能力。根据对话历史回答用户问题。

## 对话历史
{history_text if history_text else "（无历史对话）"}
{data_context_text}
{user_memory_text}

## 用户问题
{user_input}

## 回答要求
- 如果对话历史中有查询结果数据，优先根据那些数据回答用户的追问
- 如果用户质疑数据结果（如"只有这些？""什么意思？"），根据实际数据解释
- 如果历史中没有相关信息，诚实回答"不记得"
- 如果是闲聊/问候，友好自然地回应
- 简洁回答，不要过度展开
- 如果用户想查询数据但本节点无法处理，建议具体查询方式"""
    response = await llm_client.chat(prompt)
    return {
        "result": {"status": "ok", "data": None, "sql": None, "message": response.strip()},
        "agent_name": "memory_handler",
    }


async def time_node(state: AgentState) -> dict:
    """时间查询节点（确定性，零 LLM）"""
    tool = TimeTool()
    result = await tool.execute()
    if result["status"] == "ok":
        msg = f"现在是 {result['datetime']}（{result['weekday_cn']}，{result['timezone']}）"
        result["message"] = msg
    return {"result": result, "agent_name": "time_tool"}


async def _extract_city(user_input: str) -> str:
    """从用户输入抽取城市名（LLM 一次调用）

    抽不到具体城市时返回空字符串。
    """
    from app.agent.llm_client import llm_client

    prompt = (
        "从下面的用户输入中提取城市名，只输出城市名（如「北京」「上海」）。"
        "如果输入中没有提到具体城市，只输出「无」。\n\n"
        f"用户输入：{user_input}\n\n城市名："
    )
    try:
        raw = (await llm_client.chat(prompt)).strip()
    except Exception as e:
        logger.warning(f"城市抽取 LLM 调用失败: {e}")
        return ""

    if not raw or raw in ("无", "None", "没有", "不知道"):
        return ""
    return raw


async def weather_node(state: AgentState) -> dict:
    """天气查询节点（LLM 抽取城市 + 确定性 API 调用）"""
    user_input = state["user_input"]
    city = await _extract_city(user_input)
    if not city:
        return {
            "result": {
                "status": "error",
                "message": "请告诉我你想查询哪个城市的天气，例如：北京今天天气怎么样",
                "error_code": "MISSING_CITY",
            },
            "agent_name": "weather_tool",
        }

    tool = WeatherTool()
    result = await tool.execute(city)
    if result["status"] == "ok":
        result["message"] = (
            f"{result['city']}当前天气：{result['weather']}，气温{result['temp']}°C，"
            f"体感{result['feels_like']}°C，{result['wind_dir']}{result['wind_scale']}级，"
            f"湿度{result['humidity']}%"
        )
    return {"result": result, "agent_name": "weather_tool"}


async def task_plan_node(state: AgentState) -> dict:
    """任务规划节点（确定性切分，零 LLM）

    设计文档 §7：LLM 已在 classify_intent 判定 task_plan 意图，
    此处用纯函数按粒度切分，返回预览（不落库）。
    """
    user_input = state["user_input"]
    granularity, goal = parse_plan_input(user_input)
    goal = goal or "待规划任务"
    today = datetime.now().date()
    user_id = state.get("user_id", 0)

    if granularity == "today":
        items = split_today(goal, today)
    else:
        holidays, workdays, leaves = await get_workday_sets(user_id, today.year)
        if granularity == "month":
            items = split_month(goal, today.year, today.month, holidays, workdays, leaves)
        else:  # year
            items = split_year(goal, today.year, holidays, workdays, leaves)

    gran_cn = {"today": "今日", "month": "本月", "year": "本年"}[granularity]
    message = (
        f"【{gran_cn}任务规划预览】已将「{goal}」切分为 {len(items)} 个子任务，"
        f"确认后落库（目前为预览，未写入任务表）。"
    )
    return {
        "result": {
            "status": "ok",
            "data": items,
            "sql": None,
            "message": message,
            "preview": True,
        },
        "agent_name": "task_planner",
    }


# ─────────────────────────── 路由（确定性条件边） ───────────────────────────

def route_by_intent(state: AgentState) -> str:
    """按意图路由到对应执行节点（纯 Python 条件边，零 LLM）"""
    intent = state.get("intent", "unknown")
    mapping = {
        "query": "data_node",
        "report": "report_node",
        "knowledge": "knowledge_node",
        "create": "write_node",
        "update": "write_node",
        "memory": "conversation_node",
        "chat": "conversation_node",
        "time": "time_node",
        "weather": "weather_node",
        "task_plan": "task_plan_node",
    }
    return mapping.get(intent, "data_node")


def should_skip_after_security(state: AgentState) -> str:
    """安全检查失败则终止，否则继续"""
    if state.get("error") == "unsafe_input":
        return "end"
    return "continue"


# ─────────────────────────── 图构建 ───────────────────────────

def build_graph():
    """构建 LangGraph 图"""
    g = StateGraph(AgentState)

    # 节点注册（包一层进度事件，节点自身逻辑不变）
    g.add_node("security_check", security_check)
    g.add_node("save_user_message", save_user_message)
    g.add_node("classify_intent", _with_progress("正在理解问题...", classify_intent))
    g.add_node("data_node", _with_progress("正在生成 SQL 并查询数据库...", data_node))
    g.add_node("knowledge_node", _with_progress("正在检索知识库...", knowledge_node))
    g.add_node("report_node", _with_progress("正在生成报表...", report_node))
    g.add_node("write_node", _with_progress("正在执行写操作...", write_node))
    g.add_node("conversation_node", _with_progress("正在生成回答...", conversation_node))
    g.add_node("time_node", _with_progress("正在获取时间...", time_node))
    g.add_node("weather_node", _with_progress("正在查询天气...", weather_node))
    g.add_node("task_plan_node", _with_progress("正在规划任务...", task_plan_node))
    g.add_node("save_history", _with_progress("正在整理查询结果...", save_history))
    g.add_node("memory_extract", memory_extract)

    # 边：安全 → 存储 → 分类 → 路由
    g.add_edge(START, "security_check")
    g.add_conditional_edges(
        "security_check",
        should_skip_after_security,
        {"continue": "save_user_message", "end": END},
    )
    g.add_edge("save_user_message", "classify_intent")

    # 路由：确定性条件边，分发到 5 个执行节点
    g.add_conditional_edges(
        "classify_intent",
        route_by_intent,
        {
            "data_node": "data_node",
            "knowledge_node": "knowledge_node",
            "report_node": "report_node",
            "write_node": "write_node",
            "conversation_node": "conversation_node",
            "time_node": "time_node",
            "weather_node": "weather_node",
            "task_plan_node": "task_plan_node",
        },
    )

    # 执行节点 → 保存历史 → 记忆抽取 → 结束
    for node in ("data_node", "knowledge_node", "report_node", "write_node", "conversation_node", "time_node", "weather_node", "task_plan_node"):
        g.add_edge(node, "save_history")
    g.add_edge("save_history", "memory_extract")
    g.add_edge("memory_extract", END)

    return g.compile()


# 编译后的图（惰性初始化）
_compiled_graph = None


def get_graph():
    """获取编译后的图（单例）"""
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_graph()
    return _compiled_graph
