"""Query Understanding - 多意图识别与复杂度路由

职责：判断一条用户输入是「简单请求（单意图，走现有直连路由）」还是
「复杂请求（多意图/多任务，走规划路径）」。

确定性优先：先用规则判断（多句/并列连词/跨域/多意图命中），
规则无法判定时才调用 LLM 兜底。设计文档 §4.2「Query Understanding」、§4.3「Complexity Router」。
"""

import logging
import re

from app.agent.llm_client import llm_client
from app.orchestrator.planner import (
    INTENT_RULES,
    _CREATE_PRE_PATTERNS,
    _TIME_BEFORE_CREATE,
    _QUESTION_BEFORE_CREATE,
)

logger = logging.getLogger(__name__)

# 并列/顺序信号：出现这些词通常意味着多个先后或并列的任务
COORDINATION_SIGNALS = ["然后", "再", "顺便", "同时", "还有", "以及", "并且", "另外", "接着", "之后", "并且"]

# 条件/分支信号：需要条件判断 + 分支任务
CONDITION_SIGNALS = ["如果", "若", "假如", "否则", "要是"]

# 多句分隔符：同一输入被拆成多个子句，是多个问题/任务的强信号
_SENTENCE_SPLITTERS = re.compile(r"[？?。；;\n]")

# 跨域检测：查询类信号 与 写操作类信号 同时出现 → 必然多任务
_QUERY_SIGNALS = ["查", "查询", "多少", "数量", "库存", "有哪些", "有没有", "统计", "明细", "看看"]
_WRITE_SIGNALS = ["创建", "新建", "下单", "开单", "新增", "修改", "更新", "作废", "取消", "审批"]

# LLM 兜底 Prompt
QUERY_UNDERSTAND_PROMPT = """你是意图复杂度分析器。判断用户输入是「简单单意图请求」还是「复杂多任务请求」。

【判断标准】
- 简单：只包含一个明确意图（如"查询上海库存"、"你好"、"创建采购订单"）。
- 复杂：一句话里包含多个意图/多个任务/多个问题，需要拆解后分别执行（如"查库存顺便查在途然后生成补货单"）。

【对话历史】
{history}

【用户输入】
{user_input}

【输出】只输出 JSON，不要其他文字：
{{"requires_planning": true 或 false, "intents": ["意图1", "意图2"]}}"""


class QueryUnderstanding:
    """多意图识别与复杂度路由"""

    def _rules_detect(self, user_input: str) -> bool | None:
        """确定性规则判断是否需要规划

        Returns:
            bool | None: True=需要规划，False=简单请求，None=规则无法判定（交 LLM）
        """
        if not user_input or not user_input.strip():
            return False

        # 1. 多句：被句读拆成 2 个以上有效子句
        clauses = [c.strip() for c in _SENTENCE_SPLITTERS.split(user_input) if c.strip()]
        if len(clauses) >= 2:
            logger.info(f"复杂度规则命中（多句 {len(clauses)} 个子句）: {user_input[:50]}")
            return True

        # 2. 并列/顺序/条件信号
        if any(sig in user_input for sig in COORDINATION_SIGNALS) or \
           any(sig in user_input for sig in CONDITION_SIGNALS):
            logger.info(f"复杂度规则命中（并列/条件信号）: {user_input[:50]}")
            return True

        # 3. 跨域：查询信号 + 写操作信号 同时出现
        has_query = any(s in user_input for s in _QUERY_SIGNALS)
        has_write = any(s in user_input for s in _WRITE_SIGNALS)
        if has_query and has_write:
            logger.info(f"复杂度规则命中（跨域 查询+写操作）: {user_input[:50]}")
            return True

        # 3.5 单一写操作前置：创建/新增/新建 + 单据 → 单意图 create（简单）
        # 避免"创建采购订单"因"订单/采购"命中 query 关键词被误判为多意图。
        # 排除时间前缀（"4月新增销售订单"是查询）与疑问前缀（"怎么创建订单"是知识）。
        if not _TIME_BEFORE_CREATE.search(user_input) and not _QUESTION_BEFORE_CREATE.search(user_input):
            if any(re.search(pat, user_input) for pat in _CREATE_PRE_PATTERNS):
                return False

        # 4. 多意图：命中 ≥2 个不同意图类别的关键词
        hit_intents = set()
        for intent, keywords in INTENT_RULES:
            if any(kw in user_input for kw in keywords):
                hit_intents.add(intent)
        if len(hit_intents) >= 2:
            logger.info(f"复杂度规则命中（多意图 {hit_intents}）: {user_input[:50]}")
            return True

        # 5. 单意图命中：确定简单请求（单句 + 无并列 + 单意图）
        if len(hit_intents) == 1:
            return False

        # 规则无法判定（无关键词命中，可能是指代/追问）→ 交给 LLM
        return None

    async def analyze(self, user_input: str, messages: list[dict] | None = None) -> dict:
        """分析输入复杂度

        Args:
            user_input: 用户输入
            messages: 对话历史

        Returns:
            dict: {"requires_planning": bool, "intents": list[str]}
        """
        # 1. 确定性规则
        rule_result = self._rules_detect(user_input)
        if rule_result is not None:
            return {"requires_planning": rule_result, "intents": []}

        # 2. LLM 兜底
        history_text = "（无历史对话）"
        if messages:
            recent = messages[-10:]
            if recent:
                history_text = "\n".join([
                    f"{'用户' if m['role'] == 'user' else 'AI'}: {m['content'][:200]}"
                    for m in recent
                ])

        prompt = QUERY_UNDERSTAND_PROMPT.format(history=history_text, user_input=user_input)
        try:
            raw = (await llm_client.chat(prompt)).strip()
            import json
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            data = json.loads(match.group()) if match else {}
            requires = bool(data.get("requires_planning", False))
            intents = data.get("intents") if isinstance(data.get("intents"), list) else []
            logger.info(f"复杂度 LLM 判定: requires_planning={requires}, intents={intents}")
            return {"requires_planning": requires, "intents": [str(i) for i in intents]}
        except Exception as e:
            logger.warning(f"复杂度 LLM 判定失败，默认简单请求: {e}")
            return {"requires_planning": False, "intents": []}


# 全局实例
query_understanding = QueryUnderstanding()
