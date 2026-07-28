"""User Memory - 用户习惯存储

存储长期用户习惯：
- 默认查询参数
- 常用报表
- 偏好设置
"""

import json
import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import text

from app.db.session import get_session

logger = logging.getLogger(__name__)


class UserMemory:
    """用户记忆存储"""

    async def get_user_preferences(self, user_id: int) -> dict:
        """获取用户偏好设置

        Args:
            user_id: 用户 ID

        Returns:
            dict: 用户偏好设置
        """
        try:
            async for session in get_session():
                result = await session.execute(
                    text("""
                        SELECT preferences FROM user_preferences
                        WHERE user_id = :user_id
                    """),
                    {"user_id": user_id},
                )
                row = result.fetchone()

                if row and row[0]:
                    return json.loads(row[0])
                return {}

        except Exception as e:
            logger.error(f"获取用户偏好失败: {e}", exc_info=True)
            return {}

    async def update_user_preferences(self, user_id: int, preferences: dict) -> bool:
        """更新用户偏好设置

        Args:
            user_id: 用户 ID
            preferences: 偏好设置

        Returns:
            bool: 是否更新成功
        """
        try:
            async for session in get_session():
                # 检查是否已存在
                result = await session.execute(
                    text("SELECT id FROM user_preferences WHERE user_id = :user_id"),
                    {"user_id": user_id},
                )
                exists = result.fetchone()

                if exists:
                    # 更新
                    await session.execute(
                        text("""
                            UPDATE user_preferences
                            SET preferences = :preferences, updated_at = :updated_at
                            WHERE user_id = :user_id
                        """),
                        {
                            "user_id": user_id,
                            "preferences": json.dumps(preferences, ensure_ascii=False),
                            "updated_at": datetime.now(),
                        },
                    )
                else:
                    # 插入
                    await session.execute(
                        text("""
                            INSERT INTO user_preferences (user_id, preferences, created_at, updated_at)
                            VALUES (:user_id, :preferences, :created_at, :updated_at)
                        """),
                        {
                            "user_id": user_id,
                            "preferences": json.dumps(preferences, ensure_ascii=False),
                            "created_at": datetime.now(),
                            "updated_at": datetime.now(),
                        },
                    )

                await session.commit()
                logger.info(f"用户偏好更新成功: {user_id}")
                return True

        except Exception as e:
            logger.error(f"用户偏好更新失败: {e}", exc_info=True)
            return False

    async def add_recent_query(self, user_id: int, query: str, sql: str) -> bool:
        """添加最近查询记录

        Args:
            user_id: 用户 ID
            query: 用户查询
            sql: 生成的 SQL

        Returns:
            bool: 是否添加成功
        """
        try:
            preferences = await self.get_user_preferences(user_id)

            # 获取最近查询列表
            recent_queries = preferences.get("recent_queries", [])

            # 添加新查询
            recent_queries.append({
                "query": query,
                "sql": sql,
                "timestamp": datetime.now().isoformat(),
            })

            # 只保留最近 20 条
            if len(recent_queries) > 20:
                recent_queries = recent_queries[-20:]

            preferences["recent_queries"] = recent_queries

            # 更新偏好
            return await self.update_user_preferences(user_id, preferences)

        except Exception as e:
            logger.error(f"添加最近查询失败: {e}", exc_info=True)
            return False

    async def get_recent_queries(self, user_id: int, limit: int = 5) -> list[dict]:
        """获取最近查询记录

        Args:
            user_id: 用户 ID
            limit: 返回数量限制

        Returns:
            list[dict]: 最近查询列表
        """
        try:
            preferences = await self.get_user_preferences(user_id)
            recent_queries = preferences.get("recent_queries", [])
            return recent_queries[-limit:]

        except Exception as e:
            logger.error(f"获取最近查询失败: {e}", exc_info=True)
            return []

    async def get_default_filters(self, user_id: int) -> dict:
        """获取用户默认过滤条件

        Args:
            user_id: 用户 ID

        Returns:
            dict: 默认过滤条件
        """
        try:
            preferences = await self.get_user_preferences(user_id)
            return preferences.get("default_filters", {})

        except Exception as e:
            logger.error(f"获取默认过滤条件失败: {e}", exc_info=True)
            return {}


# 全局实例
user_memory = UserMemory()
