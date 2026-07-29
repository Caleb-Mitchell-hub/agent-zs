"""状态机

职责：
- 定义合法状态流转
- 校验状态变更
- 防止非法状态跳转
"""

import logging
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class TaskStatus(str, Enum):
    """任务状态"""
    PENDING = "pending"
    PLANNING = "planning"
    RUNNING = "running"
    WAITING_CONFIRM = "waiting_confirm"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class StepStatus(str, Enum):
    """步骤状态"""
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    WAITING_CONFIRM = "waiting_confirm"
    SKIPPED = "skipped"


# 合法状态流转表
TASK_VALID_TRANSITIONS = {
    TaskStatus.PENDING: [TaskStatus.PLANNING],
    TaskStatus.PLANNING: [TaskStatus.RUNNING],
    TaskStatus.RUNNING: [TaskStatus.WAITING_CONFIRM, TaskStatus.SUCCEEDED, TaskStatus.FAILED, TaskStatus.CANCELLED],
    TaskStatus.WAITING_CONFIRM: [TaskStatus.RUNNING],
    TaskStatus.FAILED: [TaskStatus.RUNNING, TaskStatus.CANCELLED],
    TaskStatus.SUCCEEDED: [],  # 终态，不可流转
    TaskStatus.CANCELLED: [],  # 终态，不可流转
}

STEP_VALID_TRANSITIONS = {
    StepStatus.PENDING: [StepStatus.RUNNING, StepStatus.SKIPPED],
    StepStatus.RUNNING: [StepStatus.SUCCEEDED, StepStatus.FAILED, StepStatus.WAITING_CONFIRM],
    StepStatus.WAITING_CONFIRM: [StepStatus.RUNNING],
    StepStatus.FAILED: [StepStatus.RUNNING],
    StepStatus.SUCCEEDED: [],  # 终态
    StepStatus.SKIPPED: [],  # 终态
}


class StateMachine:
    """状态机"""

    def validate_task_transition(self, current: str, target: str) -> bool:
        """校验任务状态流转是否合法

        Args:
            current: 当前状态
            target: 目标状态

        Returns:
            bool: 是否合法
        """
        try:
            current_status = TaskStatus(current)
            target_status = TaskStatus(target)
        except ValueError:
            logger.warning(f"无效的状态: {current} -> {target}")
            return False

        valid_targets = TASK_VALID_TRANSITIONS.get(current_status, [])

        if target_status not in valid_targets:
            logger.warning(f"非法状态流转: {current} -> {target}, 允许: {[s.value for s in valid_targets]}")
            return False

        return True

    def validate_step_transition(self, current: str, target: str) -> bool:
        """校验步骤状态流转是否合法"""
        try:
            current_status = StepStatus(current)
            target_status = StepStatus(target)
        except ValueError:
            logger.warning(f"无效的状态: {current} -> {target}")
            return False

        valid_targets = STEP_VALID_TRANSITIONS.get(current_status, [])

        if target_status not in valid_targets:
            logger.warning(f"非法状态流转: {current} -> {target}, 允许: {[s.value for s in valid_targets]}")
            return False

        return True

    def is_terminal(self, status: str) -> bool:
        """检查是否为终态"""
        return status in [TaskStatus.SUCCEEDED.value, TaskStatus.CANCELLED.value]


# 全局实例
state_machine = StateMachine()
