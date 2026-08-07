"""时间查询工具测试

验证：time 意图走确定性工具，零 LLM 调用。
"""

import pytest

from app.tools.time_tool import TimeTool


@pytest.mark.asyncio
async def test_time_tool_returns_current_time():
    """测试时间工具返回当前时间"""
    tool = TimeTool()
    result = await tool.execute()
    assert result["status"] == "ok"
    assert result["date"]  # 有日期
    assert result["time"]  # 有时间
    assert result["weekday_cn"] in ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
    assert "北京时间" in result["timezone"]


@pytest.mark.asyncio
async def test_time_tool_with_timezone():
    """测试指定时区偏移"""
    tool = TimeTool()
    result = await tool.execute(timezone_offset=0)
    assert result["status"] == "ok"
    assert result["timezone"] == "UTC+0"
