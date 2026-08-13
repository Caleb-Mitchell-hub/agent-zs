"""Weather Tool - 实时天气查询工具（和风天气 QWeather）

职责：
- 城市名 → LocationID（城市搜索接口）
- LocationID → 实时天气（实时天气接口）

注意：2025-04 起和风天气推行独立 API Host，旧公共域名（geoapi/devapi.qweather.com）
已逐步停用（返回 403 Invalid Host / 404）。必须使用控制台设置的独立 Host，
城市搜索路径带 /geo 前缀（/geo/v2/city/lookup），实时天气为 /v7/weather/now。
"""

import logging
from typing import Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class WeatherTool:
    """实时天气查询工具（和风天气后端）"""

    def _base_url(self) -> Optional[str]:
        """读取独立 API Host 并规范为完整 URL 前缀"""
        host = (settings.qweather_api_host or "").strip()
        if not host:
            return None
        # 兼容用户填 "https://xxx.qweatherapi.com" 或 "xxx.qweatherapi.com"
        if not host.startswith("http"):
            host = f"https://{host}"
        return host.rstrip("/")

    async def execute(self, city: str) -> dict:
        """查询指定城市的实时天气

        Args:
            city: 城市名称，如「北京」「上海」

        Returns:
            dict: 实时天气信息
        """
        if not city or not city.strip():
            return {"status": "error", "message": "缺少城市名", "error_code": "MISSING_CITY"}

        city = city.strip()
        api_key = settings.qweather_api_key
        base_url = self._base_url()
        if not api_key or not base_url:
            logger.warning("和风天气 API Key 或独立 Host 未配置（QWEATHER_API_KEY / QWEATHER_API_HOST）")
            return {
                "status": "error",
                "message": "天气查询服务未配置，请联系管理员配置 QWEATHER_API_KEY 与 QWEATHER_API_HOST",
                "error_code": "WEATHER_NOT_CONFIGURED",
            }

        try:
            location_id, matched_city = await self._resolve_location(city, api_key, base_url)
            if not location_id:
                return {"status": "error", "message": f"未找到城市「{city}」", "error_code": "CITY_NOT_FOUND"}

            weather = await self._fetch_now(location_id, api_key, base_url)
            if not weather:
                return {"status": "error", "message": f"查询「{city}」天气失败", "error_code": "WEATHER_FETCH_FAILED"}

            return {
                "status": "ok",
                "city": matched_city,
                "weather": weather.get("text", ""),
                "temp": weather.get("temp", ""),
                "feels_like": weather.get("feelsLike", ""),
                "humidity": weather.get("humidity", ""),
                "wind_dir": weather.get("windDir", ""),
                "wind_scale": weather.get("windScale", ""),
                "precip": weather.get("precip", ""),
                "pressure": weather.get("pressure", ""),
                "visibility": weather.get("vis", ""),
                "obs_time": weather.get("obsTime", ""),
            }

        except Exception as e:
            logger.error(f"天气查询失败: {e}", exc_info=True)
            return {"status": "error", "message": f"天气查询失败: {str(e)}", "error_code": "WEATHER_ERROR"}

    async def _resolve_location(
        self, city: str, api_key: str, base_url: str,
    ) -> tuple[Optional[str], str]:
        """城市名 → LocationID

        Returns:
            tuple: (LocationID, 匹配到的城市名)，未找到返回 (None, city)
        """
        url = f"{base_url}/geo/v2/city/lookup"
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(
                url,
                params={"location": city, "key": api_key},
            )
            if response.status_code != 200:
                logger.warning(f"城市搜索接口返回异常: {response.status_code}")
                return None, city

            data = response.json()
            if data.get("code") != "200":
                logger.warning(f"城市搜索失败: code={data.get('code')}")
                return None, city

            locations = data.get("location") or []
            if not locations:
                return None, city

            # 取第一个匹配结果
            first = locations[0]
            return first.get("id"), first.get("name", city)

    async def _fetch_now(
        self, location_id: str, api_key: str, base_url: str,
    ) -> Optional[dict]:
        """LocationID → 实时天气"""
        url = f"{base_url}/v7/weather/now"
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(
                url,
                params={"location": location_id, "key": api_key},
            )
            if response.status_code != 200:
                logger.warning(f"实时天气接口返回异常: {response.status_code}")
                return None

            data = response.json()
            if data.get("code") != "200":
                logger.warning(f"实时天气查询失败: code={data.get('code')}")
                return None

            return data.get("now")
