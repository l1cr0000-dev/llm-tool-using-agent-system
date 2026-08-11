from __future__ import annotations

import pytest

from tool_agent.tools.calculator import CalculatorTool
from tool_agent.tools.knowledge_base import KnowledgeBaseTool
from tool_agent.tools.time_tool import TimeTool
from tool_agent.tools.weather import WeatherTool


def test_calculator_evaluates_safe_arithmetic() -> None:
    result = CalculatorTool().run("请计算 2 * (3 + 4) / 7，并说明过程")

    assert result.ok is True
    assert result.data["value"] == 2


def test_calculator_rejects_unsafe_expression() -> None:
    result = CalculatorTool().run("__import__('os').system('echo bad')")

    assert result.ok is False
    assert "not allowed" in result.error.lower()


def test_knowledge_base_returns_ranked_matching_chunks(tmp_path) -> None:
    kb_file = tmp_path / "agent_notes.md"
    kb_file.write_text(
        "LangGraph is useful for stateful agent workflows.\n\n"
        "Dify is useful for low-code workflow comparison.",
        encoding="utf-8",
    )

    result = KnowledgeBaseTool(kb_dir=tmp_path).run("stateful agent graph")

    assert result.ok is True
    assert result.data["matches"][0]["source"] == "agent_notes.md"
    assert "LangGraph" in result.data["matches"][0]["text"]


def test_time_tool_resolves_city_timezone() -> None:
    result = TimeTool(now_provider=lambda tz: "2026-07-05 15:30:00 CST+0800").run("查询北京当前时间")

    assert result.ok is True
    assert result.data == {
        "location": "Beijing",
        "timezone": "Asia/Shanghai",
        "current_time": "2026-07-05 15:30:00 CST+0800",
    }


def test_weather_tool_geocodes_and_formats_current_weather() -> None:
    seen_params = {}

    class FakeClient:
        def get_json(self, url: str, params: dict[str, object]) -> dict[str, object]:
            seen_params.update(params)
            if "geocoding-api" in url:
                return {
                    "results": [
                        {
                            "name": "Beijing",
                            "country": "China",
                            "latitude": 39.91,
                            "longitude": 116.39,
                            "timezone": "Asia/Shanghai",
                        }
                    ]
                }
            return {
                "current": {
                    "temperature_2m": 31.2,
                    "precipitation": 0.0,
                    "wind_speed_10m": 8.5,
                    "weather_code": 1,
                },
                "current_units": {
                    "temperature_2m": "°C",
                    "precipitation": "mm",
                    "wind_speed_10m": "km/h",
                },
            }

    result = WeatherTool(http_client=FakeClient()).run("查询北京当前天气，并判断是否适合跑步")

    assert result.ok is True
    assert seen_params["name"] == "Beijing"
    assert result.data["location"] == "Beijing, China"
    assert result.data["temperature"] == "31.2 °C"
    assert result.data["condition"] == "Mainly clear"


def test_weather_tool_reports_missing_location() -> None:
    class FakeClient:
        def get_json(self, url: str, params: dict[str, object]) -> dict[str, object]:
            return {"results": []}

    result = WeatherTool(http_client=FakeClient()).run("Atlantis")

    assert result.ok is False
    assert "could not geocode" in result.error.lower()
