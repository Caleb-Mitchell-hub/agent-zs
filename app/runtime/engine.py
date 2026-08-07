"""Agent Runtime - 运行时引擎

职责：
- 管理 Agent 生命周期
- 执行任务步骤
- 处理错误恢复
- 记录执行日志
"""

import json
import logging
import uuid
from datetime import datetime
from enum import Enum
from typing import Optional, Callable, Any

from sqlalchemy import text

from app.db.session import get_session

logger = logging.getLogger(__name__)


class StepStatus(str, Enum):
    """步骤状态"""
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    WAITING_CONFIRM = "waiting_confirm"
    SKIPPED = "skipped"


class TaskStatus(str, Enum):
    """任务状态"""
    PENDING = "pending"
    PLANNING = "planning"
    RUNNING = "running"
    WAITING_CONFIRM = "waiting_confirm"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


# 合法状态流转
VALID_TRANSITIONS = {
    TaskStatus.PENDING: [TaskStatus.PLANNING],
    TaskStatus.PLANNING: [TaskStatus.RUNNING],
    TaskStatus.RUNNING: [TaskStatus.WAITING_CONFIRM, TaskStatus.SUCCEEDED, TaskStatus.FAILED, TaskStatus.CANCELLED],
    TaskStatus.WAITING_CONFIRM: [TaskStatus.RUNNING],
    TaskStatus.FAILED: [TaskStatus.RUNNING, TaskStatus.CANCELLED],
}


class Step:
    """任务步骤"""

    def __init__(
        self,
        step_id: str,
        step_index: int,
        tool_name: str,
        input_params: dict = None,
        depends_on: list[str] = None,
        need_confirm: bool = False,
    ):
        self.step_id = step_id
        self.step_index = step_index
        self.tool_name = tool_name
        self.input_params = input_params or {}
        self.depends_on = depends_on or []
        self.need_confirm = need_confirm
        self.status = StepStatus.PENDING
        self.output_result = None
        self.retry_count = 0
        self.last_error = None
        self.idempotency_key = None


class RuntimeEngine:
    """运行时引擎"""

    def __init__(self):
        self._tool_registry: dict[str, Callable] = {}

    def register_tool(self, tool_name: str, handler: Callable):
        """注册工具处理器"""
        self._tool_registry[tool_name] = handler

    async def create_task(
        self,
        session_id: str,
        user_id: str,
        tenant_id: str,
        goal: str,
        steps: list[Step],
    ) -> str:
        """创建任务

        Args:
            session_id: 会话ID
            user_id: 用户ID
            tenant_id: 租户ID
            goal: 任务目标
            steps: 步骤列表

        Returns:
            str: 任务ID
        """
        task_id = str(uuid.uuid4())

        try:
            async for session in get_session():
                # 创建任务
                await session.execute(
                    text("""
                        INSERT INTO tasks (task_id, session_id, user_id, tenant_id, goal, status, version)
                        VALUES (:task_id, :session_id, :user_id, :tenant_id, :goal, :status, 1)
                    """),
                    {
                        "task_id": task_id,
                        "session_id": session_id,
                        "user_id": user_id,
                        "tenant_id": tenant_id,
                        "goal": goal,
                        "status": TaskStatus.PENDING.value,
                    },
                )

                # 创建步骤
                for step in steps:
                    step.idempotency_key = f"{task_id}_{step.step_id}"
                    await session.execute(
                        text("""
                            INSERT INTO task_steps (step_id, task_id, step_index, depends_on, tool_name, input_params, need_confirm, idempotency_key, status)
                            VALUES (:step_id, :task_id, :step_index, :depends_on, :tool_name, :input_params, :need_confirm, :idempotency_key, :status)
                        """),
                        {
                            "step_id": step.step_id,
                            "task_id": task_id,
                            "step_index": step.step_index,
                            "depends_on": json.dumps(step.depends_on),
                            "tool_name": step.tool_name,
                            "input_params": json.dumps(step.input_params),
                            "need_confirm": step.need_confirm,
                            "idempotency_key": step.idempotency_key,
                            "status": StepStatus.PENDING.value,
                        },
                    )

                await session.commit()
                logger.info(f"任务创建成功: {task_id}")

                return task_id

        except Exception as e:
            logger.error(f"任务创建失败: {e}", exc_info=True)
            raise

    async def execute_task(self, task_id: str) -> dict:
        """执行任务

        Args:
            task_id: 任务ID

        Returns:
            dict: 执行结果
        """
        try:
            # 首次执行 PENDING -> PLANNING -> RUNNING；人工确认后恢复 WAITING_CONFIRM -> RUNNING
            async for session in get_session():
                result = await session.execute(
                    text("SELECT status FROM tasks WHERE task_id = :task_id"),
                    {"task_id": task_id},
                )
                row = result.fetchone()

            if not row:
                return {"status": "error", "message": f"任务不存在: {task_id}"}

            current_status = TaskStatus(row[0])
            if current_status == TaskStatus.PENDING:
                await self._update_task_status(task_id, TaskStatus.PLANNING)
                await self._update_task_status(task_id, TaskStatus.RUNNING)
            elif current_status == TaskStatus.WAITING_CONFIRM:
                await self._update_task_status(task_id, TaskStatus.RUNNING)
            elif current_status not in (TaskStatus.PLANNING, TaskStatus.RUNNING):
                return {"status": "error", "message": f"任务状态 {current_status.value} 不允许执行"}

            # 获取任务步骤
            steps = await self._get_task_steps(task_id)

            # 执行步骤
            for step in steps:
                # 恢复执行时跳过已完成的步骤
                if step.status == StepStatus.SUCCEEDED:
                    continue

                # 检查依赖是否完成
                if not await self._check_dependencies(task_id, step):
                    continue

                # 需要人工确认且尚未执行：执行前挂起，等待外部确认接口
                if step.need_confirm and step.status == StepStatus.PENDING:
                    await self._update_step_status(step.step_id, StepStatus.WAITING_CONFIRM)
                    await self._update_task_status(task_id, TaskStatus.WAITING_CONFIRM)
                    return {
                        "status": "waiting_confirm",
                        "message": f"步骤 {step.step_id} 需要人工确认后方可继续执行",
                        "task_id": task_id,
                        "step_id": step.step_id,
                    }

                # 更新步骤状态为 running
                await self._update_step_status(step.step_id, StepStatus.RUNNING)

                # 执行工具，失败按 retry_count 重试
                handler = self._tool_registry.get(step.tool_name)
                if handler is None:
                    last_error = f"工具不存在: {step.tool_name}"
                    logger.error(f"步骤执行失败: {step.step_id}, {last_error}")
                else:
                    last_error = None
                    for attempt in range(step.retry_count + 1):
                        try:
                            result = await handler(**step.input_params)

                            # 更新步骤状态为 succeeded
                            await self._update_step_status(
                                step.step_id,
                                StepStatus.SUCCEEDED,
                                output_result=result,
                            )
                            break
                        except Exception as e:
                            last_error = str(e)
                            logger.error(
                                f"步骤执行失败: {step.step_id}, 第 {attempt + 1} 次尝试, {e}",
                                exc_info=True,
                            )

                # 重试耗尽仍失败，标记失败
                if last_error is not None:
                    await self._update_step_status(
                        step.step_id,
                        StepStatus.FAILED,
                        last_error=last_error,
                    )
                    await self._update_task_status(task_id, TaskStatus.FAILED)
                    return {"status": "error", "message": last_error}

            # 更新任务状态为 succeeded
            await self._update_task_status(task_id, TaskStatus.SUCCEEDED)

            return {"status": "ok", "task_id": task_id}

        except Exception as e:
            logger.error(f"任务执行失败: {e}", exc_info=True)
            try:
                await self._update_task_status(task_id, TaskStatus.FAILED)
            except Exception:
                logger.warning(f"更新任务状态为 FAILED 失败: {task_id}", exc_info=True)
            return {"status": "error", "message": str(e)}

    async def confirm_step(self, task_id: str, step_id: str, confirmed_user: str) -> dict:
        """人工确认步骤后继续执行

        Args:
            task_id: 任务ID
            step_id: 步骤ID
            confirmed_user: 确认人ID

        Returns:
            dict: 继续执行结果
        """
        async for session in get_session():
            result = await session.execute(
                text("SELECT task_id, status FROM task_steps WHERE step_id = :step_id"),
                {"step_id": step_id},
            )
            row = result.fetchone()

            if not row:
                return {"status": "error", "message": f"步骤不存在: {step_id}"}

            if row[0] != task_id:
                return {"status": "error", "message": f"步骤 {step_id} 不属于任务 {task_id}"}

            if row[1] != StepStatus.WAITING_CONFIRM.value:
                return {"status": "error", "message": f"步骤 {step_id} 不在等待确认状态"}

            await session.execute(
                text("""
                    UPDATE task_steps
                    SET status = :status, confirmed_by = :confirmed_by,
                        confirmed_at = :confirmed_at, updated_at = :updated_at
                    WHERE step_id = :step_id
                """),
                {
                    "status": StepStatus.RUNNING.value,
                    "confirmed_by": confirmed_user,
                    "confirmed_at": datetime.now(),
                    "updated_at": datetime.now(),
                    "step_id": step_id,
                },
            )
            await session.commit()

        logger.info(f"步骤 {step_id} 已由 {confirmed_user} 确认，继续执行任务 {task_id}")
        return await self.execute_task(task_id)

    async def _check_dependencies(self, task_id: str, step: Step) -> bool:
        """检查步骤依赖是否完成"""
        if not step.depends_on:
            return True

        async for session in get_session():
            for dep_step_id in step.depends_on:
                result = await session.execute(
                    text("SELECT status FROM task_steps WHERE step_id = :step_id"),
                    {"step_id": dep_step_id},
                )
                row = result.fetchone()
                if not row or row[0] != StepStatus.SUCCEEDED.value:
                    return False

            return True

    async def _update_task_status(self, task_id: str, new_status: TaskStatus):
        """更新任务状态（校验状态流转合法性）

        Args:
            task_id: 任务ID
            new_status: 目标状态

        Raises:
            ValueError: 任务不存在或状态流转非法
        """
        async for session in get_session():
            result = await session.execute(
                text("SELECT status FROM tasks WHERE task_id = :task_id"),
                {"task_id": task_id},
            )
            row = result.fetchone()

            if not row:
                raise ValueError(f"任务不存在: {task_id}")

            current_status = TaskStatus(row[0])

            if new_status not in VALID_TRANSITIONS.get(current_status, []):
                raise ValueError(
                    f"非法状态流转: {current_status.value} -> {new_status.value}"
                )

            await session.execute(
                text("""
                    UPDATE tasks SET status = :status, updated_at = :updated_at
                    WHERE task_id = :task_id
                """),
                {"status": new_status.value, "updated_at": datetime.now(), "task_id": task_id},
            )
            await session.commit()

    async def _update_step_status(
        self,
        step_id: str,
        status: StepStatus,
        output_result: dict = None,
        last_error: str = None,
    ):
        """更新步骤状态"""
        async for session in get_session():
            update_fields = {
                "status": status.value,
                "updated_at": datetime.now(),
                "step_id": step_id,
            }

            if output_result:
                await session.execute(
                    text("""
                        UPDATE task_steps SET status = :status, output_result = :output_result, updated_at = :updated_at
                        WHERE step_id = :step_id
                    """),
                    {**update_fields, "output_result": json.dumps(output_result)},
                )
            elif last_error:
                await session.execute(
                    text("""
                        UPDATE task_steps SET status = :status, last_error = :last_error, updated_at = :updated_at
                        WHERE step_id = :step_id
                    """),
                    {**update_fields, "last_error": last_error},
                )
            else:
                await session.execute(
                    text("UPDATE task_steps SET status = :status, updated_at = :updated_at WHERE step_id = :step_id"),
                    update_fields,
                )

            await session.commit()

    async def _get_task_steps(self, task_id: str) -> list[Step]:
        """获取任务步骤"""
        async for session in get_session():
            result = await session.execute(
                text("SELECT * FROM task_steps WHERE task_id = :task_id ORDER BY step_index"),
                {"task_id": task_id},
            )
            rows = result.mappings().all()

            steps = []
            for row in rows:
                step = Step(
                    step_id=row["step_id"],
                    step_index=row["step_index"],
                    tool_name=row["tool_name"],
                    input_params=json.loads(row["input_params"]) if row["input_params"] else {},
                    depends_on=json.loads(row["depends_on"]) if row["depends_on"] else [],
                    need_confirm=row.get("need_confirm", False),
                )
                step.status = StepStatus(row["status"])
                step.retry_count = row.get("retry_count", 0)
                steps.append(step)

            return steps

    async def get_task_status(self, task_id: str) -> dict:
        """获取任务状态"""
        async for session in get_session():
            result = await session.execute(
                text("SELECT * FROM tasks WHERE task_id = :task_id"),
                {"task_id": task_id},
            )
            row = result.mappings().first()

            if not row:
                return {"status": "error", "message": "任务不存在"}

            # 获取步骤状态
            steps_result = await session.execute(
                text("SELECT step_id, step_index, tool_name, status FROM task_steps WHERE task_id = :task_id ORDER BY step_index"),
                {"task_id": task_id},
            )
            steps = [dict(s) for s in steps_result.mappings().all()]

            return {
                "task_id": row["task_id"],
                "goal": row["goal"],
                "status": row["status"],
                "current_step_id": row["current_step_id"],
                "steps": steps,
                "created_at": str(row["created_at"]),
                "updated_at": str(row["updated_at"]),
            }


# 全局实例
runtime = RuntimeEngine()
