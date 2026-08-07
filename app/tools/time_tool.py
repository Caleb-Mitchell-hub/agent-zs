"""Time Tool - 实时时间查询工具"""

import logging
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

# 北京时间时区
CST = timezone(timedelta(hours=8))


class TimeTool:
    """实时时间查询工具"""

    async def execute(self, timezone_offset: int | None = None) -> dict:
        """获取当前时间

        Args:
            timezone_offset: 时区偏移量（小时），默认返回北京时间 (UTC+8)

        Returns:
            dict: 当前时间信息
        """
        try:
            if timezone_offset is not None:
                tz = timezone(timedelta(hours=timezone_offset))
            else:
                tz = CST

            now = datetime.now(tz)

            return {
                "status": "ok",
                "datetime": now.strftime("%Y-%m-%d %H:%M:%S"),
                "date": now.strftime("%Y-%m-%d"),
                "time": now.strftime("%H:%M:%S"),
                "weekday": now.strftime("%A"),
                "weekday_cn": ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"][now.weekday()],
                "timestamp": int(now.timestamp()),
                "timezone": f"UTC{timezone_offset:+d}" if timezone_offset is not None else "UTC+8 (北京时间)",
            }
        except Exception as e:
            logger.error(f"时间查询失败: {e}", exc_info=True)
            return {"status": "error", "message": str(e)}
