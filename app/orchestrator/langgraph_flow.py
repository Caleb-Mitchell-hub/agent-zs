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
from app.orchestrator.planner import planner, extract_task_title
from app.tools.follow_up_router import should_reuse_result, compose_reuse_reply
from app.tools.time_tool import TimeTool
from app.tools.weather_tool import WeatherTool
from app.agents.data_agent import DataAgent
from app.agents.write_agent import WriteAgent
from app.agents.knowledge_agent import KnowledgeAgent
from app.agents.report_agent import ReportAgent
from app.tasks.planner import parse_plan_input, split_today, split_month, split_year
from app.tasks.service import get_workday_sets, create_task
from app.policy.engine import evaluate_policy, PolicyDecision

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
    user_permissions: dict   # 数据范围权限（ABAC）
    user_info: dict          # 用户完整信息（roles/is_super_admin，供 RBAC 判定）
    requires_planning: bool  # 是否走多任务规划路径
    plan: dict               # Plan IR（任务计划）
    plan_results: list[dict] # 各子任务执行结果
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


def _check_policy(action: str, state: AgentState) -> dict | None:
    """执行前统一权限判定（RBAC / 风险）

    返回 None 表示放行，可继续执行；否则返回拒绝/待确认结果，节点直接返回该结果。

    所有能力（读 query/report/knowledge、写 create/update）执行前都必须经此判定，
    杜绝「简单路径绕过 Policy Engine」的漏洞。
    """
    decision = evaluate_policy(action, state.get("user_info"))
    if decision == PolicyDecision.DENY:
        logger.warning(f"权限拦截: 拒绝执行 {action} (user={state.get('user_id')})")
        return {"status": "denied", "message": f"无权限执行 {action} 操作", "error_code": "PERMISSION_DENIED"}
    if decision == PolicyDecision.REQUIRE_CONFIRMATION:
        logger.warning(f"权限拦截: {action} 需人工确认 (user={state.get('user_id')})")
        return {"status": "waiting_confirm", "message": f"{action} 操作需要人工确认后执行", "error_code": "REQUIRE_CONFIRMATION"}
    return None


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
    # 权限判定（RBAC）：读操作默认放行，命中禁用角色则拒绝
    denied = _check_policy("query", state)
    if denied is not None:
        return {"result": denied, "agent_name": "data_agent"}

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
    denied = _check_policy("knowledge", state)
    if denied is not None:
        return {"result": denied, "agent_name": "knowledge_agent"}
    agent = KnowledgeAgent()
    result = await agent.execute(
        state["user_input"], state.get("messages") or [], state.get("context") or {},
        state["session_id"], state.get("user_id", 0), state.get("tenant_id", 1),
    )
    return {"result": result, "agent_name": "knowledge_agent"}


async def report_node(state: AgentState) -> dict:
    """报表节点（模板优先，未命中 LLM 兜底）"""
    denied = _check_policy("report", state)
    if denied is not None:
        return {"result": denied, "agent_name": "report_agent"}
    agent = ReportAgent()
    result = await agent.execute(
        state["user_input"], state.get("messages") or [], state.get("context") or {},
        state["session_id"], state.get("user_id", 0), state.get("tenant_id", 1),
    )
    return {"result": result, "agent_name": "report_agent"}


async def write_node(state: AgentState) -> dict:
    """写操作节点（LLM 参数抽取 + ERP 调用）"""
    # 权限判定：create 校验写权限，update 额外强制人工确认
    action = "update" if state.get("intent") == "update" else "create"
    denied = _check_policy(action, state)
    if denied is not None:
        return {"result": denied, "agent_name": "write_agent"}
    agent = WriteAgent()
    result = await agent.execute(
        state["user_input"], state.get("messages") or [], state.get("context") or {},
        state["session_id"], state.get("user_id", 0), state.get("tenant_id", 1),
        state.get("user_permissions"),
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


async def task_create_node(state: AgentState) -> dict:
    """创建任务节点（确定性，零 LLM）

    意图已由 classify_intent 判定为 task_create，此处用正则提取标题，
    直接落库 user_tasks，返回创建结果（前端据此刷新任务列表）。
    """
    user_input = state["user_input"]
    title = extract_task_title(user_input)
    user_id = state.get("user_id", 0)
    await create_task(user_id, title)
    return {
        "result": {
            "status": "ok",
            "data": None,
            "sql": None,
            "message": f"✅ 已创建任务「{title}」",
            "task_created": True,
        },
        "agent_name": "task_creator",
    }


# ─────────────────────────── 多任务编排节点 ───────────────────────────

async def query_understanding_node(state: AgentState) -> dict:
    """多意图识别与复杂度路由（确定性规则优先，LLM 兜底）"""
    from app.orchestrator.query_understanding import query_understanding
    analysis = await query_understanding.analyze(
        state["user_input"], state.get("messages"),
    )
    return {"requires_planning": analysis["requires_planning"]}


async def planning_node(state: AgentState) -> dict:
    """任务规划：LLM 把用户请求拆解为 Plan IR（多任务 + 依赖）"""
    plan = await planner.plan_task(state["user_input"], state.get("messages"))
    return {"plan": plan.model_dump()}


async def plan_validate_node(state: AgentState) -> dict:
    """计划校验（确定性）：action 合法 / 依赖存在 / 环检测"""
    from app.orchestrator.plan_schema import Plan
    from app.orchestrator.plan_validator import validate_plan
    plan = Plan.model_validate(state["plan"])
    check = validate_plan(plan)
    if not check["valid"]:
        logger.error(f"计划校验失败: {check['errors']}")
        return {
            "result": {"status": "error", "message": "任务规划失败：" + "；".join(check["errors"])},
            "error": "invalid_plan",
        }
    return {}


async def execute_plan_node(state: AgentState) -> dict:
    """执行计划：DAG 拓扑分层并行调度（设计文档 §11「DAG Scheduler」）

    按拓扑分层，每层内无依赖步骤用 asyncio.gather 并行执行；
    层间串行（下一层依赖上一层的输出，通过步骤间传参 $step_id.output 注入）。
    """
    import asyncio
    from app.orchestrator.plan_schema import Plan
    from app.orchestrator.plan_validator import topological_layers
    from app.orchestrator.task_executor import task_executor, resolve_params
    from app.policy.engine import evaluate_policy, PolicyDecision

    plan = Plan.model_validate(state["plan"])
    layers = topological_layers(plan)
    steps_by_id = {s.id: s for s in plan.steps}

    results_by_step: dict[str, dict] = {}
    plan_results: list[dict] = []

    messages = state.get("messages") or []
    context = state.get("context") or {}
    session_id = state["session_id"]
    user_id = state.get("user_id", 0)
    tenant_id = state.get("tenant_id", 1)
    user_permissions = state.get("user_permissions") or {}
    user_info = state.get("user_info") or {}

    # 落库：复用 RuntimeEngine 持久化任务/步骤快照（Phase 2 持久化恢复数据源）
    # 失败不阻塞主流程（仅审计/恢复用途，非致命）
    from app.runtime.engine import runtime, Step as RuntimeStep, StepStatus as RuntimeStepStatus
    task_id = None
    try:
        task_id = await runtime.create_task(
            str(session_id), str(user_id), str(tenant_id), plan.goal,
            [
                RuntimeStep(
                    step_id=s.id,
                    step_index=i,
                    tool_name=s.action,  # action 即能力标识（query/create/...）
                    input_params=s.params,
                    depends_on=s.after,
                )
                for i, s in enumerate(plan.steps)
            ],
        )
    except Exception as e:
        logger.warning(f"计划落库失败（非致命，继续执行）: {e}")

    async def persist_step(step_id: str, result: dict) -> None:
        """步骤结果落库（非致命，失败仅记录日志）"""
        if not task_id:
            return
        try:
            status = result.get("status")
            if status == "ok":
                await runtime._update_step_status(step_id, RuntimeStepStatus.SUCCEEDED, output_result=result)
            elif status == "waiting_confirm":
                await runtime._update_step_status(step_id, RuntimeStepStatus.WAITING_CONFIRM)
            else:
                await runtime._update_step_status(step_id, RuntimeStepStatus.FAILED, last_error=result.get("message", ""))
        except Exception as e:
            logger.warning(f"步骤状态落库失败（非致命）: {e}")

    for layer in layers:
        async def run_one(step_id: str):
            step = steps_by_id[step_id]
            # 1. Policy 判定（RBAC / 风险）
            decision = evaluate_policy(step.action, user_info)
            if decision == PolicyDecision.DENY:
                result = {"status": "denied", "message": f"无权限执行 {step.action}"}
            elif decision == PolicyDecision.REQUIRE_CONFIRMATION:
                result = {"status": "waiting_confirm", "message": f"{step.action} 需要人工确认后执行"}
            else:
                # 2. 步骤间传参（注入上游输出）
                resolved = resolve_params(step.params, results_by_step)
                # 3. 执行步骤
                result = await task_executor.execute_step(
                    step, resolved, messages, context,
                    session_id, user_id, tenant_id, user_permissions,
                )
            await persist_step(step_id, result)
            return step_id, result

        layer_results = await asyncio.gather(*[run_one(sid) for sid in layer])
        for step_id, result in layer_results:
            results_by_step[step_id] = result
            plan_results.append({
                "step_id": step_id,
                "action": steps_by_id[step_id].action,
                "result": result,
            })

    return {"plan_results": plan_results, "task_id": task_id}


async def aggregate_node(state: AgentState) -> dict:
    """结果聚合：把多个子任务结果汇总成一段连贯回答"""
    from app.orchestrator.aggregator import aggregator
    plan_results = state.get("plan_results") or []
    message = await aggregator.aggregate(state["user_input"], plan_results)
    return {
        "result": {"status": "ok", "data": None, "sql": None, "message": message},
        "agent_name": "planner",
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
        "task_create": "task_create_node",
    }
    return mapping.get(intent, "data_node")


def route_after_understanding(state: AgentState) -> str:
    """复杂度路由：复杂请求走规划路径，简单请求走原单意图路由（零回归）"""
    if state.get("requires_planning"):
        return "planning"
    return route_by_intent(state)


def route_after_validate(state: AgentState) -> str:
    """计划校验失败直接落库结束，否则执行计划"""
    if state.get("error") == "invalid_plan":
        return "save_history"
    return "execute_plan"


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
    g.add_node("task_create_node", _with_progress("正在创建任务...", task_create_node))
    g.add_node("query_understanding", _with_progress("正在分析请求...", query_understanding_node))
    g.add_node("planning", _with_progress("正在拆解任务...", planning_node))
    g.add_node("plan_validate", plan_validate_node)
    g.add_node("execute_plan", _with_progress("正在并行执行任务...", execute_plan_node))
    g.add_node("aggregate", _with_progress("正在汇总结果...", aggregate_node))
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
    g.add_edge("classify_intent", "query_understanding")

    # 复杂度路由：复杂请求走规划，简单请求走原单意图路由（零回归）
    g.add_conditional_edges(
        "query_understanding",
        route_after_understanding,
        {
            "planning": "planning",
            "data_node": "data_node",
            "knowledge_node": "knowledge_node",
            "report_node": "report_node",
            "write_node": "write_node",
            "conversation_node": "conversation_node",
            "time_node": "time_node",
            "weather_node": "weather_node",
            "task_plan_node": "task_plan_node",
            "task_create_node": "task_create_node",
        },
    )

    # 规划路径：规划 → 校验 → (执行计划 → 聚合) / (失败 → 落库)
    g.add_edge("planning", "plan_validate")
    g.add_conditional_edges(
        "plan_validate",
        route_after_validate,
        {"execute_plan": "execute_plan", "save_history": "save_history"},
    )
    g.add_edge("execute_plan", "aggregate")
    g.add_edge("aggregate", "save_history")

    # 执行节点 → 保存历史 → 记忆抽取 → 结束
    for node in ("data_node", "knowledge_node", "report_node", "write_node", "conversation_node", "time_node", "weather_node", "task_plan_node", "task_create_node"):
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
