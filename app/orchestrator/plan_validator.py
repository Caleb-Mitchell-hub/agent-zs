"""Plan Validator - 计划校验

LLM 生成的 Plan IR 不能直接执行，必须先经过确定性校验（设计文档 §6）：
1. action 合法性（白名单，禁止 LLM 创造不存在的动作）
2. after 依赖引用存在 + 不自依赖
3. 环检测（拓扑排序）
4. 步骤间传参引用合法（$step_id.output.xxx 形式）

同时提供 topological_layers() 供 execute_plan 做 DAG 并行调度。
"""

import logging
import re
from collections import defaultdict, deque

from app.orchestrator.plan_schema import Plan, VALID_ACTIONS

logger = logging.getLogger(__name__)

# 步骤间传参引用：$s1.output.field 或 $s1.output
_REF_PATTERN = re.compile(r"\$([A-Za-z_][\w]*)(?:\.output(?:\.\w+)?)?")


def _has_cycle(plan: Plan) -> bool:
    """拓扑排序检测环（Kahn 算法）"""
    indegree = {s.id: 0 for s in plan.steps}
    adj: dict[str, list[str]] = defaultdict(list)
    for s in plan.steps:
        for dep in s.after:
            adj[dep].append(s.id)  # dep -> s
            indegree[s.id] += 1

    queue = deque([sid for sid, d in indegree.items() if d == 0])
    visited = 0
    while queue:
        node = queue.popleft()
        visited += 1
        for nxt in adj[node]:
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                queue.append(nxt)
    return visited != len(plan.steps)


def validate_plan(plan: Plan) -> dict:
    """校验计划

    Args:
        plan: 计划对象

    Returns:
        dict: {"valid": bool, "errors": list[str]}
    """
    errors: list[str] = []
    step_ids = {s.id for s in plan.steps}

    # 1. 步骤 id 唯一性
    if len(step_ids) != len(plan.steps):
        errors.append("步骤 id 存在重复")

    # 2. action 合法性
    for s in plan.steps:
        if s.action not in VALID_ACTIONS:
            errors.append(f"步骤 {s.id} 的 action 非法: {s.action}（合法值: {', '.join(sorted(VALID_ACTIONS))}）")

    # 3. after 依赖引用存在 + 不自依赖
    for s in plan.steps:
        for dep in s.after:
            if dep == s.id:
                errors.append(f"步骤 {s.id} 不能依赖自身")
            elif dep not in step_ids:
                errors.append(f"步骤 {s.id} 依赖不存在的步骤: {dep}")

    # 4. 步骤间传参引用合法（$step_id.output.xxx）
    for s in plan.steps:
        for val in s.params.values():
            if isinstance(val, str):
                for ref in _REF_PATTERN.findall(val):
                    if ref not in step_ids:
                        errors.append(f"步骤 {s.id} 引用了不存在的步骤: ${ref}")

    # 5. 环检测（仅在依赖引用合法时进行，避免误报）
    if not errors and _has_cycle(plan):
        errors.append("计划存在循环依赖")

    return {"valid": not errors, "errors": errors}


def topological_layers(plan: Plan) -> list[list[str]]:
    """按拓扑排序返回分层：每层内的步骤无相互依赖，可并行执行

    Args:
        plan: 已通过校验的计划

    Returns:
        list[list[str]]: 每层是 step_id 列表，层间顺序为执行顺序
    """
    indegree = {s.id: 0 for s in plan.steps}
    adj: dict[str, list[str]] = defaultdict(list)
    for s in plan.steps:
        for dep in s.after:
            adj[dep].append(s.id)
            indegree[s.id] += 1

    layers: list[list[str]] = []
    current = [sid for sid, d in indegree.items() if d == 0]
    while current:
        layers.append(sorted(current))
        nxt: list[str] = []
        for node in current:
            for child in adj[node]:
                indegree[child] -= 1
                if indegree[child] == 0:
                    nxt.append(child)
        current = nxt
    return layers
