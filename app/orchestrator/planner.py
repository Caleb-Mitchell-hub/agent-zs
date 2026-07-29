"""任务规划器

职责：
- 两级意图理解
- 任务分解
- 执行计划生成
"""

import logging
from typing import Optional

from app.agent.llm_client import llm_client

logger = logging.getLogger(__name__)

# 意图分类 Prompt
INTENT_CLASSIFY_PROMPT = """你是一个意图分类专家。将用户输入分类为以下类别之一：

类别：
- query: 查询数据、统计、分析
- create: 创建单据（采购订单、销售订单等）
- update: 更新单据状态
- report: 生成报表、图表
- knowledge: 查询知识、规则、流程
- chat: 闲聊、问候

用户输入: {user_input}

只返回类别名称，不要解释。"""


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

    async def classify_intent(self, user_input: str) -> str:
        """意图分类

        Args:
            user_input: 用户输入

        Returns:
            str: 意图类别
        """
        prompt = INTENT_CLASSIFY_PROMPT.format(user_input=user_input)
        response = await llm_client.chat(prompt)
        return response.strip().lower()

    async def plan_task(self, goal: str) -> list[dict]:
        """规划任务

        Args:
            goal: 任务目标

        Returns:
            list[dict]: 执行步骤
        """
        import re
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
