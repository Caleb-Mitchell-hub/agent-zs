"""天气查询工具测试"""

import pytest

from app.config import settings
from app.tools.weather_tool import WeatherTool


@pytest.mark.asyncio
async def test_missing_city():
    """缺少城市名返回错误"""
    tool = WeatherTool()
    result = await tool.execute("")
    assert result["status"] == "error"
    assert result["error_code"] == "MISSING_CITY"


@pytest.mark.asyncio
async def test_key_not_configured(monkeypatch):
    """未配置 API Key 返回明确错误"""
    monkeypatch.setattr(settings, "qweather_api_key", "")
    monkeypatch.setattr(settings, "qweather_api_host", "demo.qweatherapi.com")
    tool = WeatherTool()
    result = await tool.execute("北京")
    assert result["status"] == "error"
    assert result["error_code"] == "WEATHER_NOT_CONFIGURED"


@pytest.mark.asyncio
async def test_host_not_configured(monkeypatch):
    """未配置独立 API Host 返回明确错误"""
    monkeypatch.setattr(settings, "qweather_api_key", "test-key")
    monkeypatch.setattr(settings, "qweather_api_host", "")
    tool = WeatherTool()
    result = await tool.execute("北京")
    assert result["status"] == "error"
    assert result["error_code"] == "WEATHER_NOT_CONFIGURED"


@pytest.mark.asyncio
async def test_weather_query_ok(monkeypatch):
    """正常天气查询（mock 城市解析与实时天气接口）"""
    monkeypatch.setattr(settings, "qweather_api_key", "test-key")
    monkeypatch.setattr(settings, "qweather_api_host", "demo.re.qweatherapi.com")

    async def fake_resolve(self, city, api_key, base_url):
        return "101010100", "北京"

    async def fake_fetch(self, location_id, api_key, base_url):
        return {
            "text": "晴",
            "temp": "5",
            "feelsLike": "1",
            "humidity": "40",
            "windDir": "东北风",
            "windScale": "3",
            "precip": "0.0",
            "pressure": "1020",
            "vis": "10",
            "obsTime": "2026-08-13T10:00+08:00",
        }

    monkeypatch.setattr(WeatherTool, "_resolve_location", fake_resolve)
    monkeypatch.setattr(WeatherTool, "_fetch_now", fake_fetch)

    tool = WeatherTool()
    result = await tool.execute("北京")
    assert result["status"] == "ok"
    assert result["city"] == "北京"
    assert result["weather"] == "晴"
    assert result["temp"] == "5"
    assert result["humidity"] == "40"


@pytest.mark.asyncio
async def test_city_not_found(monkeypatch):
    """城市未找到返回错误"""
    monkeypatch.setattr(settings, "qweather_api_key", "test-key")
    monkeypatch.setattr(settings, "qweather_api_host", "demo.re.qweatherapi.com")

    async def fake_resolve(self, city, api_key, base_url):
        return None, city

    monkeypatch.setattr(WeatherTool, "_resolve_location", fake_resolve)

    tool = WeatherTool()
    result = await tool.execute("不存在的城市")
    assert result["status"] == "error"
    assert result["error_code"] == "CITY_NOT_FOUND"
