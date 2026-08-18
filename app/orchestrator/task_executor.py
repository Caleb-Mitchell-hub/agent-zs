"""Task Executor - 统一任务步骤分发执行

将 PlanStep（action + params）分发到对应 Agent 执行，并支持：
- 步骤间传参（$step_id.output.xxx 引用上游步骤结果）
- 统一返回结构（dict 含 status）

复用现有 4 个 Agent（DataAgent/WriteAgent/ReportAgent/KnowledgeAgent），不新造执行逻辑。
"""

import logging
import re

from app.orchestrator.plan_schema import PlanStep
from app.agents.data_agent import DataAgent
from app.agents.write_agent import WriteAgent
from app.agents.report_agent import ReportAgent
from app.agents.knowledge_agent import KnowledgeAgent

logger = logging.getLogger(__name__)

# 步骤间传参引用：$step_id 或 $step_id.output 或 $step_id.output.field
_REF_RE = re.compile(r"\$([A-Za-z_][\w]*)(?:\.output(?:\.(\w+))?)?")

# 单据类型 → 中文名（用于把 create/update 步骤转成自然语言输入）
_DOC_TYPE_NAMES = {
    "purchase_order": "采购订单",
    "sales_order": "销售订单",
    "stock_in_order": "入库单",
    "stock_out_order": "出库单",
    "expense_reimbursement": "报销单",
}


def _resolve_refs(text: str, results_by_step: dict[str, dict]) -> str:
    """替换文本中的 $step_id.output.xxx 引用为上游结果值"""
    def _repl(match: re.Match) -> str:
        step_id = match.group(1)
        field = match.group(2)
        result = results_by_step.get(step_id) or {}
        if field:
            val = result.get(field)
            return str(val) if val is not None else match.group(0)
        return str(result)

    return _REF_RE.sub(_repl, text)


def resolve_params(params: dict, results_by_step: dict[str, dict]) -> dict:
    """解析步骤入参：把其中的 $step_id.output.xxx 引用替换为上游步骤结果

    Args:
        params: 原始入参
        results_by_step: 已执行步骤的结果映射 {step_id: result_dict}

    Returns:
        dict: 解析后的入参
    """
    resolved: dict = {}
    for k, v in params.items():
        if isinstance(v, str) and "$" in v:
            resolved[k] = _resolve_refs(v, results_by_step)
        else:
            resolved[k] = v
    return resolved


class TaskExecutor:
    """统一任务步骤执行器"""

    def _build_user_input(self, step: PlanStep, params: dict) -> str:
        """把步骤 params 转成 Agent 可理解的自然语言输入"""
        action = step.action

        if action in ("query", "report", "knowledge"):
            q = params.get("question") or params.get("query") or ""
            if q:
                return str(q)
            # 兜底：拼接除 question/query 外的参数
            return " ".join(
                f"{k}{v}" for k, v in params.items()
                if k not in ("question", "query") and v
            )

        # create / update
        doc_type = params.get("doc_type", "")
        doc_name = _DOC_TYPE_NAMES.get(doc_type, doc_type or "单据")
        verb = "创建" if action == "create" else "更新"
        fields = params.get("params") or params
        parts = [f"{verb}{doc_name}"]
        for k, v in fields.items():
            if k in ("doc_type", "params"):
                continue
            if v:
                parts.append(f"{k}为{v}")
        return "，".join(parts)

    async def execute_step(
        self,
        step: PlanStep,
        resolved_params: dict,
        messages: list[dict],
        context: dict,
        session_id: str,
        user_id: int,
        tenant_id: int,
        user_permissions: dict | None = None,
    ) -> dict:
        """执行单个步骤

        Args:
            step: 计划步骤
            resolved_params: 已解析传参的入参
            messages: 对话历史
            context: 会话上下文
            session_id: 会话 ID
            user_id: 用户 ID
            tenant_id: 租户 ID
            user_permissions: 数据范围权限

        Returns:
            dict: 执行结果（统一含 status 字段）
        """
        user_input = self._build_user_input(step, resolved_params)
        action = step.action
        logger.info(f"执行步骤 {step.id} (action={action}): {user_input[:60]}")

        try:
            if action == "query":
                agent = DataAgent()
                return await agent.execute(
                    user_input, messages, context, session_id,
                    user_id, tenant_id, user_permissions,
                )
            elif action in ("create", "update"):
                agent = WriteAgent()
                return await agent.execute(
                    user_input, messages, context, session_id, user_id, tenant_id,
                )
            elif action == "report":
                agent = ReportAgent()
                return await agent.execute(
                    user_input, messages, context, session_id, user_id, tenant_id,
                )
            elif action == "knowledge":
                agent = KnowledgeAgent()
                return await agent.execute(
                    user_input, messages, context, session_id, user_id, tenant_id,
                )
            else:
                return {"status": "error", "message": f"不支持的 action: {action}"}
        except Exception as e:
            logger.error(f"步骤 {step.id} 执行异常: {e}", exc_info=True)
            return {"status": "error", "message": f"步骤 {step.id} 执行失败: {e}"}


# 全局实例
task_executor = TaskExecutor()
