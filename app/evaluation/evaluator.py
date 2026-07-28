"""Agent 评估系统

职责：
- 评估 Agent 性能
- 记录评估结果
- 生成评估报告
"""

import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import text

from app.db.session import get_session

logger = logging.getLogger(__name__)


class AgentEvaluator:
    """Agent 评估器"""

    async def evaluate_task(
        self,
        task_id: str,
        agent_name: str,
        user_id: int,
        tenant_id: int,
        metrics: dict,
    ) -> dict:
        """评估任务

        Args:
            task_id: 任务 ID
            agent_name: Agent 名称
            user_id: 用户 ID
            tenant_id: 租户 ID
            metrics: 评估指标 {
                "accuracy": float,  # 准确率
                "latency_ms": int,  # 延迟
                "user_satisfaction": int,  # 用户满意度 (1-5)
                "error_count": int,  # 错误次数
            }

        Returns:
            dict: 评估结果
        """
        try:
            # 计算综合分数
            score = self._calculate_score(metrics)

            async for session in get_session():
                await session.execute(
                    text("""
                        INSERT INTO agent_evaluation (
                            task_id, agent_name, user_id, tenant_id,
                            accuracy, latency_ms, user_satisfaction,
                            error_count, score,
                            created_at
                        ) VALUES (
                            :task_id, :agent_name, :user_id, :tenant_id,
                            :accuracy, :latency_ms, :user_satisfaction,
                            :error_count, :score,
                            :created_at
                        )
                    """),
                    {
                        "task_id": task_id,
                        "agent_name": agent_name,
                        "user_id": user_id,
                        "tenant_id": tenant_id,
                        "accuracy": metrics.get("accuracy", 0),
                        "latency_ms": metrics.get("latency_ms", 0),
                        "user_satisfaction": metrics.get("user_satisfaction", 0),
                        "error_count": metrics.get("error_count", 0),
                        "score": score,
                        "created_at": datetime.now(),
                    },
                )
                await session.commit()

                logger.info(f"任务评估完成: {task_id}, 分数: {score}")

                return {
                    "status": "ok",
                    "score": score,
                    "metrics": metrics,
                }

        except Exception as e:
            logger.error(f"任务评估失败: {e}", exc_info=True)
            return {"status": "error", "message": f"任务评估失败: {str(e)}"}

    async def get_agent_performance(
        self,
        agent_name: str,
        tenant_id: int,
        days: int = 7,
    ) -> dict:
        """获取 Agent 性能统计

        Args:
            agent_name: Agent 名称
            tenant_id: 租户 ID
            days: 统计天数

        Returns:
            dict: 性能统计
        """
        try:
            async for session in get_session():
                result = await session.execute(
                    text("""
                        SELECT
                            COUNT(*) as total_tasks,
                            AVG(score) as avg_score,
                            AVG(accuracy) as avg_accuracy,
                            AVG(latency_ms) as avg_latency,
                            AVG(user_satisfaction) as avg_satisfaction,
                            SUM(error_count) as total_errors
                        FROM agent_evaluation
                        WHERE agent_name = :agent_name
                          AND tenant_id = :tenant_id
                          AND created_at >= DATE_SUB(NOW(), INTERVAL :days DAY)
                    """),
                    {"agent_name": agent_name, "tenant_id": tenant_id, "days": days},
                )
                row = result.fetchone()

                if row:
                    return {
                        "status": "ok",
                        "performance": {
                            "agent_name": agent_name,
                            "period_days": days,
                            "total_tasks": row[0],
                            "avg_score": round(row[1], 2) if row[1] else 0,
                            "avg_accuracy": round(row[2], 2) if row[2] else 0,
                            "avg_latency_ms": round(row[3], 2) if row[3] else 0,
                            "avg_satisfaction": round(row[4], 2) if row[4] else 0,
                            "total_errors": row[5],
                        },
                    }
                else:
                    return {
                        "status": "ok",
                        "performance": {
                            "agent_name": agent_name,
                            "period_days": days,
                            "total_tasks": 0,
                        },
                    }

        except Exception as e:
            logger.error(f"获取 Agent 性能失败: {e}", exc_info=True)
            return {"status": "error", "message": f"获取 Agent 性能失败: {str(e)}"}

    async def get_evaluation_report(self, tenant_id: int, days: int = 7) -> dict:
        """获取评估报告

        Args:
            tenant_id: 租户 ID
            days: 统计天数

        Returns:
            dict: 评估报告
        """
        try:
            async for session in get_session():
                # 获取各 Agent 性能
                result = await session.execute(
                    text("""
                        SELECT
                            agent_name,
                            COUNT(*) as total_tasks,
                            AVG(score) as avg_score,
                            AVG(latency_ms) as avg_latency
                        FROM agent_evaluation
                        WHERE tenant_id = :tenant_id
                          AND created_at >= DATE_SUB(NOW(), INTERVAL :days DAY)
                        GROUP BY agent_name
                    """),
                    {"tenant_id": tenant_id, "days": days},
                )
                rows = result.fetchall()

                agents = []
                for row in rows:
                    agents.append({
                        "agent_name": row[0],
                        "total_tasks": row[1],
                        "avg_score": round(row[2], 2) if row[2] else 0,
                        "avg_latency_ms": round(row[3], 2) if row[3] else 0,
                    })

                return {
                    "status": "ok",
                    "report": {
                        "period_days": days,
                        "agents": agents,
                    },
                }

        except Exception as e:
            logger.error(f"获取评估报告失败: {e}", exc_info=True)
            return {"status": "error", "message": f"获取评估报告失败: {str(e)}"}

    def _calculate_score(self, metrics: dict) -> float:
        """计算综合分数

        Args:
            metrics: 评估指标

        Returns:
            float: 综合分数 (0-100)
        """
        accuracy = metrics.get("accuracy", 0)
        latency_ms = metrics.get("latency_ms", 0)
        user_satisfaction = metrics.get("user_satisfaction", 0)
        error_count = metrics.get("error_count", 0)

        # 准确率分数 (40%)
        accuracy_score = accuracy * 40

        # 延迟分数 (20%) - 越低越好
        if latency_ms < 1000:
            latency_score = 20
        elif latency_ms < 3000:
            latency_score = 15
        elif latency_ms < 5000:
            latency_score = 10
        else:
            latency_score = 5

        # 用户满意度分数 (30%)
        satisfaction_score = (user_satisfaction / 5) * 30

        # 错误分数 (10%) - 越少越好
        if error_count == 0:
            error_score = 10
        elif error_count <= 2:
            error_score = 5
        else:
            error_score = 0

        total_score = accuracy_score + latency_score + satisfaction_score + error_score
        return round(total_score, 2)


# 全局实例
evaluator = AgentEvaluator()
