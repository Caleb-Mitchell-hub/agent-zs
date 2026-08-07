"""任务规划器

职责：
- 意图理解（规则引擎优先：打分制 + 置信度判定 → 无歧义直接返回；歧义/未命中 → LLM 兜底）
- 任务分解
- 执行计划生成

设计文档 §2.2「确定性优先」：规则引擎打分判定无歧义时直接返回，不调用 LLM；
只有当多意图比分接近（歧义）或完全无关键词命中时，才调用 LLM 结合上下文判断。
这样既保证了确定性场景的低延迟和零成本，又能在长尾/省略/指代场景利用 LLM 的语义理解能力。
"""

import logging
import re
from typing import Optional

from app.agent.llm_client import llm_client

logger = logging.getLogger(__name__)

# 意图规则表（打分制，每个意图对应一组关键词，命中关键词按长度之和计分）
# 关键词越长/越具体，权重越高
INTENT_RULES = [
    # 记忆/回顾
    ("memory", [
        "记得", "之前说", "之前聊", "刚才", "聊了什么", "我问了",
        "上一轮", "刚才说了", "之前问了", "我还说过", "回顾",
    ]),
    # 时间/日期（只匹配明确的纯时间询问，避免误命中含"今天""日期"的业务查询）
    ("time", [
        "几点", "几号", "星期几",
        "当前时间", "现在时间", "日历",
    ]),
    # 闲聊/问候
    ("chat", [
        "你好", "您好", "你是谁", "谢谢", "再见", "哈喽", "嗨",
        "早上好", "中午好", "晚上好", "在吗", "介绍一下", "你能做什么",
    ]),
    # 创建单据（只保留明确的创建动词，避免与 report/knowledge/update 冲突）
    ("create", [
        "创建", "新建", "下单", "开单", "建单",
        "帮我创建", "请帮我创建",
    ]),
    # 更新状态
    ("update", [
        "修改", "更新", "变更", "改为", "改成", "审批通过",
        "确认收货", "提交审批", "驳回", "作废", "取消订单",
        "改成已完成", "状态改为",
    ]),
    # 报表
    ("report", [
        "报表", "图表", "趋势", "汇总", "统计图", "柱状", "折线",
        "饼图", "分析报告", "可视化", "排名", "占比",
    ]),
    # 知识/规则/流程
    ("knowledge", [
        "流程", "规则", "制度", "怎么", "如何", "什么是",
        "指南", "手册", "说明", "步骤", "标准", "规范",
        "允许", "不允许", "可以吗",
    ]),
    # 查询（默认放最后，覆盖面最广）
    ("query", [
        "查询", "查一下", "多少", "数量", "库存", "订单", "销售",
        "采购", "明细", "列表", "单号", "金额", "统计", "看看",
        "有哪些", "有没有", "在哪", "什么时候",
    ]),
]

# 规则引擎置信度阈值：当多个意图命中时，只有当最高分 >= 次高分 × RATIO 时才判定为无歧义
# 比值越大越保守（更多请求交给 LLM），越小越激进（更多请求由规则直接裁决）
_RULE_CONFIDENCE_RATIO = 2.0

# 合法意图集合（LLM 输出校验白名单，防止脏数据透传到下游路由）
VALID_INTENTS = {"query", "create", "update", "report", "knowledge", "memory", "time", "chat"}

# 意图分类 Prompt
INTENT_CLASSIFY_PROMPT = """你是一名专业的用户意图分类器，需要根据对话上下文和当前用户输入判断其所属意图类别。

【分类规则】
请严格从以下类别中选择一个最符合的类别：

- query：
  用户希望查询已有数据、统计信息、业务数据、数据分析结果。
  示例：
  “查询本月销售额”
  “统计今年采购数量”
  “分析客户订单情况”

- create：
  用户希望创建新的业务单据或记录。
  示例：
  “创建一个采购订单”
  “生成销售合同”
  “新增客户信息”

- update：
  用户希望修改、更新已有单据或业务数据状态。
  示例：
  “修改订单金额”
  “把采购单改成已完成”
  “更新订单状态”

- report：
  用户希望生成报表、图表、数据可视化结果。
  示例：
  “生成销售报表”
  “制作订单趋势图”
  “输出月度分析报告”

- knowledge：
  用户希望查询知识、业务规则、操作流程、制度说明等非业务数据内容。
  示例：
  “采购流程是什么”
  “退货规则有哪些”
  “如何申请报销”

- memory：
  用户询问历史对话、之前讨论内容、是否记得上下文。
  关键词包括：
  “记得吗”
  “之前说过”
  “刚才聊了什么”
  “你还记得我的问题吗”

- time：
  用户询问当前时间、日期、星期几等实时时间信息。
  示例：
  “现在几点”
  “今天几号”
  “当前日期”
  “星期一还是二”

- chat：
  闲聊、问候、自我介绍、非业务请求。
  示例：
  “你好”
  “你是谁”
  “今天天气不错”

【判断要求】
1. 必须结合对话上下文理解用户当前输入的真正意图。
2. 如果当前输入是省略表达、指代词或追问（如”那北京呢？””按地区分””改成华为”），必须根据对话历史推断其完整意图。
3. 只能输出一个类别名称。
4. 不要输出解释、原因、示例或其他文字。
5. 如果多个类别都符合，选择用户主要目的对应的类别。
6. 输出必须严格匹配以下格式：

query / create / update / report / knowledge / memory / time / chat

【对话历史】
{conversation_history}

【当前用户输入】
{user_input}

【输出】"""


# 任务规划 Prompt
TASK_PLAN_PROMPT = """你是一个任务规划专家。根据用户目标，规划执行步骤。

## 用户目标
{goal}

## 可用工具
- query_tool: 查询数据库
- create_document: 创建单据
- approval_tool: 审批流程
- report_tool: 生成报表
- knowledge_tool: 知识检索
- image_parser: 图片解析

## 输出格式
返回 JSON：
{{
    "steps": [
        {{"id": 1, "tool": "工具名", "description": "步骤描述", "params": {{}}, "depends_on": []}},
        {{"id": 2, "tool": "工具名", "description": "步骤描述", "params": {{}}, "depends_on": [1]}}
    ]
}}

## JSON"""


class Planner:
    """任务规划器"""

    def _classify_by_rules(self, user_input: str) -> Optional[str]:
        """规则引擎分类：打分制 + 置信度判定

        遍历所有意图的所有关键词，按命中关键词长度之和计分：
        - 无命中 → 返回 None（交给 LLM）
        - 仅一个意图命中 → 直接返回该意图（无歧义）
        - 多个意图命中 → 最高分 >= 次高分 × 阈值 时返回最高分意图；
          否则视为歧义，返回 None（交给 LLM）

        Args:
            user_input: 用户输入

        Returns:
            Optional[str]: 确定性意图类别，None 表示需 LLM 判断
        """
        if not user_input or not user_input.strip():
            return None

        # 计算每个意图的得分：命中关键词长度之和
        scores: dict[str, int] = {}
        hit_details: dict[str, list[str]] = {}

        for intent, keywords in INTENT_RULES:
            matched = [kw for kw in keywords if kw in user_input]
            if matched:
                scores[intent] = sum(len(kw) for kw in matched)
                hit_details[intent] = matched

        # 无命中
        if not scores:
            logger.debug(f"规则引擎无命中: {user_input[:50]}")
            return None

        # 单意图命中，无歧义直接返回
        if len(scores) == 1:
            intent = next(iter(scores))
            logger.info(
                f"规则引擎单意图命中: {intent} "
                f"（关键词: {hit_details[intent]}，得分: {scores[intent]}）"
            )
            return intent

        # 多意图命中：按得分降序，置信度判定
        sorted_intents = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        top_intent, top_score = sorted_intents[0]
        second_intent, second_score = sorted_intents[1]
        ratio = top_score / second_score if second_score > 0 else float("inf")

        if top_score >= second_score * _RULE_CONFIDENCE_RATIO:
            logger.info(
                f"规则引擎判定无歧义: {top_intent} "
                f"（得分 {top_score}，次高 {second_intent}={second_score}，"
                f"比值 {ratio:.1f} >= {_RULE_CONFIDENCE_RATIO}）"
            )
            return top_intent

        # 比分接近，歧义，交给 LLM
        logger.info(
            f"规则引擎判定歧义，转 LLM: "
            f"top={top_intent}({top_score}) vs 2nd={second_intent}({second_score})，"
            f"比值 {ratio:.1f} < {_RULE_CONFIDENCE_RATIO}，"
            f"所有命中: {dict(scores)}"
        )
        return None

    async def classify_intent(self, user_input: str, messages: list[dict] | None = None) -> str:
        """意图分类：规则引擎优先，LLM 兜底

        流程：
        1. 规则引擎打分判定 — 无歧义时直接返回，不调用 LLM（零延迟、零成本）
        2. 歧义或未命中 → 调用 LLM（带对话上下文），输出做合法性校验
           （校验失败兜底返回 "query"，不向透传脏数据）

        Args:
            user_input: 用户输入
            messages: 对话历史消息列表

        Returns:
            str: 意图类别
        """
        # 空输入
        if not user_input or not user_input.strip():
            return "unknown"

        # 1. 规则引擎优先：打分判定无歧义时直接返回
        rule_result = self._classify_by_rules(user_input)
        if rule_result is not None:
            return rule_result

        # 2. 规则引擎无法裁决 → LLM 兜底（带对话上下文）
        history_text = "（无历史对话）"
        if messages:
            recent = messages[-20:]  # 最近20条消息（10轮对话）
            if recent:
                history_text = "\n".join([
                    f"{'用户' if m['role'] == 'user' else 'AI'}: {m['content'][:300]}"
                    for m in recent
                ])

        prompt = INTENT_CLASSIFY_PROMPT.format(
            conversation_history=history_text,
            user_input=user_input,
        )
        llm_raw = (await llm_client.chat(prompt)).strip().lower()

        # 3. LLM 输出合法性校验：防止夹带解释文字或非法类别透传到下游
        if llm_raw not in VALID_INTENTS:
            logger.warning(
                f"LLM 输出非法意图类别，兜底为 query: "
                f"raw='{llm_raw[:100]}'，输入='{user_input[:50]}'"
            )
            return "query"

        logger.info(f"LLM 分类: {llm_raw}（输入: {user_input[:50]}）")
        return llm_raw

    async def plan_task(self, goal: str) -> list[dict]:
        """规划任务

        Args:
            goal: 任务目标

        Returns:
            list[dict]: 执行步骤
        """
        import json

        prompt = TASK_PLAN_PROMPT.format(goal=goal)
        response = await llm_client.chat(prompt)

        # 解析 JSON
        match = re.search(r'\{.*\}', response, re.DOTALL)
        if match:
            plan = json.loads(match.group())
            return plan.get("steps", [])
        else:
            return []


# 全局实例
planner = Planner()
