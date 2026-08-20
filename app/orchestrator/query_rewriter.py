"""Query Rewriter - 查询改写 / 指代消解节点

职责：在 data_node 进入 NL→SQL 之前，把用户省略的追问补全成完整、自包含的查询。

背景：此前系统靠 NL_TO_SQL 的 context_hint 弱提示让 LLM 自己「悟」多轮语义，
遇到「查询王横的」这类缺主语的追问，LLM 宁可反问（CLARIFY）也不猜，
导致用户换个人名就无法延续上一轮的单据类型。

设计文档 §2.2「确定性优先」：先确定性判断「是否需要改写」（避免每条查询都多调一次
LLM），命中才调用 LLM 做指代消解 / 对象补全。

触发条件（全部满足才改写）：
1. 存在上一轮查询（context 里有 last_query）
2. 当前输入未包含明确的业务对象词（订单/库存/仓库/采购/销售…），即省略了对象

改写依据：上一轮问题 + 上一轮 SQL（据此继承「我」映射到的人员字段，如 created_by）。
"""

import logging

from app.agent.llm_client import llm_client

logger = logging.getLogger(__name__)

# 业务对象词：输入里出现这些词，说明用户已明确表达查询对象，无需补全
BUSINESS_OBJECT_KEYWORDS = [
    "订单", "采购", "销售", "库存", "仓库", "入库", "出库",
    "应付", "应收", "报销", "客户", "供应商", "商品", "产品",
    "SKU", "sku", "报表", "明细", "待处理", "待办", "用户",
    "员工", "角色", "部门", "审批", "任务", "单号", "金额",
]

QUERY_REWRITE_PROMPT = """你是查询改写器。根据对话历史与上一轮查询，把用户省略的追问补全成一句完整、自包含的中文查询。

## 对话历史（最近几轮）
{history}

## 上一轮查询
- 用户问题: {last_query}
- 执行的 SQL: {last_sql}

## 用户当前输入（可能是省略句 / 追问）
{user_input}

## 改写要求
1. 补全用户省略的「业务对象」：上一轮查的是「销售订单」，用户只说「查询王横的」，应补全为「查询王横的销售订单」。
2. 继承「人员维度」：上一轮若是「查询我的XX」（我=当前用户），用户换成具体人名时，沿用上一轮 SQL 里「我」使用的过滤字段（created_by 或 salesman_id）来理解该人名。例如上一轮 SQL 用 created_by 过滤，则理解为「查询王横创建的销售订单」；用 salesman_id，则理解为「查询销售员王横的销售订单」。
3. 继承「条件维度」：「北京呢」「上个月呢」这类换条件追问，沿用上一轮查询结构，只替换条件值。
4. 只补全省略的信息，不改变用户已明确表达的内容。
5. 只输出一句完整、自包含的中文查询，不要 SQL，不要解释，不要加引号。

## 改写后的完整查询"""


def _build_history(messages: list[dict]) -> str:
    """构建最近几轮对话历史摘要"""
    if not messages:
        return "（无历史对话）"
    lines = []
    for msg in messages[-6:]:
        if msg.get("role") == "user":
            lines.append(f"用户: {msg.get('content', '')}")
        elif msg.get("role") == "assistant":
            lines.append(f"AI: {msg.get('content', '')[:200]}")
    return "\n".join(lines) if lines else "（无历史对话）"


def needs_query_rewrite(user_input: str, context: dict) -> bool:
    """确定性判断当前输入是否需要改写（省略了业务对象）

    Returns:
        bool: True = 需要补全对象/消解指代；False = 输入已自包含，直接走原查询
    """
    if not context.get("last_query"):
        return False
    if not user_input or not user_input.strip():
        return False
    # 已含业务对象词 → 自包含，无需改写
    if any(kw in user_input for kw in BUSINESS_OBJECT_KEYWORDS):
        return False
    return True


async def rewrite_if_needed(user_input: str, messages: list[dict], context: dict) -> str:
    """查询改写入口：需要改写则调用 LLM 补全，否则原样返回。

    Args:
        user_input: 用户当前输入
        messages: 对话历史
        context: 会话上下文（含 last_query / last_sql / last_result）

    Returns:
        str: 改写后的完整查询（无需改写或改写失败时返回原始输入）
    """
    if not needs_query_rewrite(user_input, context):
        return user_input

    last_query = context.get("last_query", "")
    last_sql = context.get("last_sql")
    if not last_sql:
        last_result = context.get("last_result")
        if isinstance(last_result, dict):
            last_sql = last_result.get("sql")
    last_sql = last_sql or "（无）"

    prompt = QUERY_REWRITE_PROMPT.format(
        history=_build_history(messages),
        last_query=last_query,
        last_sql=last_sql,
        user_input=user_input,
    )
    try:
        rewritten = (await llm_client.chat(prompt)).strip()
    except Exception as e:
        logger.warning(f"查询改写 LLM 调用失败，沿用原始输入: {e}")
        return user_input

    if not rewritten or rewritten == user_input:
        return user_input

    logger.info(f"查询改写: 「{user_input}」→「{rewritten}」")
    return rewritten
