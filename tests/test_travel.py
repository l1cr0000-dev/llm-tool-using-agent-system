from __future__ import annotations

from typer.testing import CliRunner

from tool_agent.cli import app
from tool_agent.travel import TravelPlanner, TravelRequest


def test_travel_planner_renders_itinerary_and_budget_from_tool_results() -> None:
    def fake_runner(_: str):
        return {
            "tool_results": [
                {
                    "tool": "transport_quote",
                    "ok": True,
                    "data": {
                        "recommended": {"mode": "高铁二等座", "duration_hours": 5, "cost_cny": 600},
                        "options": [
                            {"mode": "高铁二等座", "duration_hours": 5, "cost_cny": 600},
                            {"mode": "经济舱", "duration_hours": 4, "cost_cny": 900},
                        ],
                    },
                },
                {
                    "tool": "destination_guide",
                    "ok": True,
                    "data": {
                        "attractions": [
                            {"name": "博物馆", "ticket_cny": 0, "tags": ["历史"]},
                            {"name": "古城", "ticket_cny": 40, "tags": ["历史"]},
                        ],
                        "restaurants": [{"name": "本地餐厅", "cuisine": "地方菜", "avg_cost_cny": 100}],
                        "daily_cost": {"lodging_cny": 400, "food_cny": 180, "local_transport_cny": 50},
                    },
                },
            ]
        }

    plan = TravelPlanner(agent_runner=fake_runner).create_plan(
        TravelRequest(origin="上海", destination="北京", days=2, budget_cny=2500, interests=("历史",))
    )

    assert "# 北京 2 日旅行计划" in plan
    assert "| 第 1 天 | 博物馆" in plan
    assert "总计：¥2540 / 人" in plan
    assert "预计超出 ¥40" in plan


def test_travel_cli_runs_offline_end_to_end() -> None:
    result = CliRunner().invoke(
        app,
        ["travel", "上海", "北京", "--days", "2", "--budget", "4000", "--interests", "历史,美食", "--offline"],
    )

    assert result.exit_code == 0
    assert "# 北京 2 日旅行计划" in result.output
    assert "往返交通" in result.output
    assert "四季民福烤鸭店" in result.output
