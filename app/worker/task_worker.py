"""Task Worker - 异步任务执行器

职责：
- 异步执行任务
- 心跳上报
- 僵尸任务检测
"""

import logging
import asyncio
from datetime import datetime, timedelta

from sqlalchemy import text

from app.db.session import get_session
from app.runtime.engine import runtime

logger = logging.getLogger(__name__)


class TaskWorker:
    """任务 Worker"""

    def __init__(self):
        self._running = False

    async def start(self):
        """启动 Worker"""
        self._running = True
        logger.info("Task Worker 启动")

        # 启动心跳上报
        asyncio.create_task(self._heartbeat_loop())

        # 启动僵尸任务检测
        asyncio.create_task(self._zombie_detection_loop())

    async def stop(self):
        """停止 Worker"""
        self._running = False
        logger.info("Task Worker 停止")

    async def _heartbeat_loop(self):
        """心跳上报循环"""
        while self._running:
            try:
                await self._update_heartbeat()
                await asyncio.sleep(30)  # 每30秒上报一次
            except Exception as e:
                logger.error(f"心跳上报失败: {e}")
                await asyncio.sleep(10)

    async def _zombie_detection_loop(self):
        """僵尸任务检测循环"""
        while self._running:
            try:
                await self._detect_zombie_tasks()
                await asyncio.sleep(60)  # 每60秒检测一次
            except Exception as e:
                logger.error(f"僵尸任务检测失败: {e}")
                await asyncio.sleep(10)

    async def _update_heartbeat(self):
        """更新心跳时间"""
        try:
            async for session in get_session():
                await session.execute(
                    text("""
                        UPDATE task_steps SET heartbeat_at = :heartbeat
                        WHERE status = 'running'
                    """),
                    {"heartbeat": datetime.now()},
                )
                await session.commit()
        except Exception as e:
            logger.warning(f"更新心跳失败: {e}")

    async def _detect_zombie_tasks(self):
        """检测僵尸任务"""
        try:
            async for session in get_session():
                # 查找超过5分钟没有心跳的 running 步骤
                result = await session.execute(
                    text("""
                        SELECT ts.step_id, ts.task_id, ts.tool_name, ts.heartbeat_at
                        FROM task_steps ts
                        WHERE ts.status = 'running'
                          AND ts.heartbeat_at < DATE_SUB(NOW(), INTERVAL 5 MINUTE)
                    """)
                )
                zombies = result.fetchall()

                for zombie in zombies:
                    logger.warning(f"检测到僵尸任务: {zombie[1]} - {zombie[0]}")

                    # 标记为失败
                    await session.execute(
                        text("""
                            UPDATE task_steps SET status = 'failed', last_error = 'Worker心跳超时'
                            WHERE step_id = :step_id
                        """),
                        {"step_id": zombie[0]},
                    )

                    # 更新任务状态
                    await session.execute(
                        text("""
                            UPDATE tasks SET status = 'failed', updated_at = :updated_at
                            WHERE task_id = :task_id
                        """),
                        {"task_id": zombie[1], "updated_at": datetime.now()},
                    )

                await session.commit()

                if zombies:
                    logger.info(f"处理了 {len(zombies)} 个僵尸任务")

        except Exception as e:
            logger.warning(f"僵尸任务检测失败: {e}")


# 全局实例
task_worker = TaskWorker()
