"""Plan IR 数据模型

中间表示（IR）：LLM 规划器只负责表达「要做什么 + 任务之间的关系」，
具体执行约束（timeout/retry/permission/risk）由代码层（TaskExecutor/Policy Engine）补全。
设计文档 §5「Plan IR」。
"""

from pydantic import BaseModel, Field

# 合法 action 白名单：对应现有 4 个 Agent 的能力
# query → DataAgent；create/update → WriteAgent；report → ReportAgent；knowledge → KnowledgeAgent
VALID_ACTIONS = {"query", "create", "update", "report", "knowledge"}

# action → 执行节点/Agent 的映射（供 TaskExecutor 分发，单一事实来源）
ACTION_AGENT_MAP = {
    "query": "data_agent",
    "create": "write_agent",
    "update": "write_agent",
    "report": "report_agent",
    "knowledge": "knowledge_agent",
}


class PlanStep(BaseModel):
    """单个任务步骤

    Attributes:
        id: 步骤唯一标识（如 s1/s2/s3）
        action: 能力名称（VALID_ACTIONS 之一）
        params: 步骤入参（如 {"question": "...", "doc_type": "..."}）
        after: 依赖的前置步骤 ID 列表（空表示无依赖，可与同级并行）
    """
    id: str
    action: str
    params: dict = Field(default_factory=dict)
    after: list[str] = Field(default_factory=list)


class Plan(BaseModel):
    """任务计划

    Attributes:
        goal: 计划目标（用户请求的整体目标概述）
        steps: 步骤列表
    """
    goal: str
    steps: list[PlanStep]


def plan_from_dict(data: dict) -> Plan:
    """从字典构造 Plan（容忍 LLM 输出的字段差异，如 steps 缺省/非法类型）

    Args:
        data: LLM 输出的计划字典

    Returns:
        Plan: 校验后的计划对象

    Raises:
        ValueError: 缺少 goal 或 steps 字段
    """
    if not isinstance(data, dict):
        raise ValueError("计划输出不是 JSON 对象")
    goal = data.get("goal") or ""
    steps_raw = data.get("steps")
    if not isinstance(steps_raw, list) or not steps_raw:
        raise ValueError("计划缺少 steps 字段或为空")

    steps = []
    for i, s in enumerate(steps_raw):
        if not isinstance(s, dict):
            continue
        steps.append(PlanStep(
            id=s.get("id") or f"s{i + 1}",
            action=(s.get("action") or "").strip().lower(),
            params=s.get("params") or {},
            after=s.get("after") or s.get("depends_on") or [],
        ))
    if not steps:
        raise ValueError("计划 steps 为空")

    return Plan(goal=goal, steps=steps)
