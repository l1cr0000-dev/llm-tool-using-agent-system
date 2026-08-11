from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests

from tool_agent.tools.base import ToolResult


WEATHER_CODES = {
    # Open-Meteo 返回 weather_code 数字；这里转成人类可读描述。
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    71: "Slight snow",
    73: "Moderate snow",
    75: "Heavy snow",
    80: "Slight rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    95: "Thunderstorm",
}

LOCATION_ALIASES = {
    # Open-Meteo geocoding 对整句中文问题不一定稳定，所以先做轻量城市抽取。
    "北京": "Beijing",
    "beijing": "Beijing",
    "上海": "Shanghai",
    "shanghai": "Shanghai",
    "纽约": "New York",
    "new york": "New York",
    "伦敦": "London",
    "london": "London",
    "东京": "Tokyo",
    "tokyo": "Tokyo",
    "巴黎": "Paris",
    "paris": "Paris",
}


@dataclass(slots=True)
class RequestsJsonClient:
    """HTTP JSON 客户端薄封装。

    单独封装是为了测试 WeatherTool 时可以注入 fake client，不真正请求网络。
    """

    timeout: float = 10.0

    def get_json(self, url: str, params: dict[str, object]) -> dict[str, Any]:
        response = requests.get(url, params=params, timeout=self.timeout)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError("weather API returned non-object JSON")
        return data


class WeatherTool:
    """当前天气工具。

    流程：
    1. 从自然语言 query 中抽取城市；
    2. 调 Open-Meteo Geocoding API 获取经纬度；
    3. 调 Forecast API 获取当前温度、降水、风速和天气码。
    """

    name = "get_weather"

    def __init__(self, http_client: RequestsJsonClient | None = None) -> None:
        self.http_client = http_client or RequestsJsonClient()

    def run(self, query: str) -> ToolResult:
        location_query = self._extract_location(query)
        if not location_query:
            return ToolResult(ok=False, tool=self.name, error="location is required")
        try:
            location = self._geocode(location_query)
            forecast = self._forecast(location)
        except Exception as exc:
            return ToolResult(ok=False, tool=self.name, error=str(exc))
        return ToolResult(ok=True, tool=self.name, data=forecast)

    def _geocode(self, query: str) -> dict[str, Any]:
        # Open-Meteo geocoding 不需要 API key，适合作品集 demo。
        data = self.http_client.get_json(
            "https://geocoding-api.open-meteo.com/v1/search",
            {"name": query, "count": 1, "language": "en", "format": "json"},
        )
        results = data.get("results") or []
        if not results:
            raise ValueError(f"could not geocode location: {query}")
        first = results[0]
        if not isinstance(first, dict):
            raise ValueError("geocoding API returned malformed result")
        return first

    def _extract_location(self, query: str) -> str:
        cleaned = query.strip()
        lowered = cleaned.lower()
        for alias, location in LOCATION_ALIASES.items():
            if alias in lowered or alias in cleaned:
                return location
        return cleaned

    def _forecast(self, location: dict[str, Any]) -> dict[str, Any]:
        # current 参数只取当前 demo 需要的字段，避免返回过大的天气数据。
        data = self.http_client.get_json(
            "https://api.open-meteo.com/v1/forecast",
            {
                "latitude": location["latitude"],
                "longitude": location["longitude"],
                "current": "temperature_2m,precipitation,wind_speed_10m,weather_code",
                "timezone": location.get("timezone", "auto"),
            },
        )
        current = data.get("current") or {}
        units = data.get("current_units") or {}
        code = int(current.get("weather_code", -1))
        name = location.get("name", "Unknown")
        country = location.get("country", "")
        return {
            "location": f"{name}, {country}".strip(", "),
            "timezone": location.get("timezone"),
            "temperature": f"{current.get('temperature_2m')} {units.get('temperature_2m', '')}".strip(),
            "precipitation": f"{current.get('precipitation')} {units.get('precipitation', '')}".strip(),
            "wind_speed": f"{current.get('wind_speed_10m')} {units.get('wind_speed_10m', '')}".strip(),
            "condition": WEATHER_CODES.get(code, f"Weather code {code}"),
        }
