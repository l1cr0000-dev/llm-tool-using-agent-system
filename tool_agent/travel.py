"""Travel itinerary assembly on top of the generic Agent graph."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Callable

from tool_agent.graph import run_agent


@dataclass(frozen=True, slots=True)
class TravelRequest:
    origin: str
    destination: str
    days: int = 3
    budget_cny: int | None = None
    interests: tuple[str, ...] = ()

    def validate(self) -> None:
        if not self.origin.strip() or not self.destination.strip():
            raise ValueError("origin and destination are required")
        if not 1 <= self.days <= 14:
            raise ValueError("days must be between 1 and 14")
        if self.budget_cny is not None and self.budget_cny <= 0:
            raise ValueError("budget must be a positive amount")


class TravelPlanner:
    """Uses the existing agent to collect facts, then renders a traceable itinerary."""

    def __init__(self, agent_runner: Callable[[str], dict[str, Any]] | None = None, graph=None) -> None:
        self._graph = graph
        self._agent_runner = agent_runner

    def create_plan(self, request: TravelRequest) -> str:
        request.validate()
        result = self._run_agent(request)
        data = self._tool_data(result)
        transport = data.get("transport_quote")
        guide = data.get("destination_guide")
        if not transport or not guide:
            missing = "、".join(name for name, value in {"交通报价": transport, "目的地指南": guide}.items() if not value)
            return f"# {request.destination} {request.days} 日旅行计划\n\n暂无法生成完整计划，缺少：{missing}。请配置联网搜索或选择内置目的地。"

        attractions = self._rank_attractions(guide["attractions"], request.interests)
        restaurants = guide["restaurants"]
        daily_cost = guide["daily_cost"]
        itinerary, daily_totals = self._build_itinerary(request.days, attractions, restaurants, daily_cost)
        transport_cost = int(transport["recommended"]["cost_cny"]) * 2
        total = transport_cost + sum(daily_totals)
        budget_line = self._budget_line(request.budget_cny, total)
        options = "；".join(
            f"{item['mode']}：约 {item['duration_hours']} 小时 / ¥{item['cost_cny']}（单程）"
            for item in transport["options"]
        )
        interests = "、".join(request.interests) if request.interests else "综合体验"
        return "\n".join(
            [
                f"# {request.destination} {request.days} 日旅行计划",
                "",
                f"> 出发地：{request.origin} ｜ 偏好：{interests} ｜ 费用均为单人估算（人民币）",
                "",
                "## 往返交通",
                f"- 推荐：{transport['recommended']['mode']}，单程约 {transport['recommended']['duration_hours']} 小时，¥{transport['recommended']['cost_cny']}；往返预计 ¥{transport_cost}。",
                f"- 备选：{options}。",
                "",
                "## 每日行程",
                "",
                "| 天数 | 上午 | 下午 | 用餐推荐 | 当日预估 |",
                "| --- | --- | --- | --- | ---: |",
                *itinerary,
                "",
                "## 消费汇总",
                f"- 行程与餐饮住宿：¥{sum(daily_totals)}",
                f"- 往返交通：¥{transport_cost}",
                f"- **总计：¥{total} / 人**",
                f"- {budget_line}",
                "",
                "## 预订建议",
                "- 景点票价、餐厅排队和交通价格会随日期变化；出发前请以官方渠道和实际订单为准。",
                "- 需要实时航班、酒店或天气时，在请求中加入“最新”，并配置 `TAVILY_API_KEY` 让 Agent 补充联网搜索。",
            ]
        )

    def _run_agent(self, request: TravelRequest) -> dict[str, Any]:
        question = (
            f"旅游计划；出发地: {request.origin}；目的地: {request.destination}；"
            f"天数: {request.days}；预算: {request.budget_cny or '未设置'}；"
            f"偏好: {','.join(request.interests) or '综合体验'}"
        )
        if self._agent_runner:
            return self._agent_runner(question)
        return run_agent(question, graph=self._graph, thread_id=str(uuid.uuid4()))

    def _tool_data(self, result: dict[str, Any]) -> dict[str, dict[str, Any]]:
        return {
            str(item["tool"]): item["data"]
            for item in result.get("tool_results", [])
            if item.get("ok") and isinstance(item.get("data"), dict)
        }

    def _rank_attractions(self, attractions: list[dict[str, Any]], interests: tuple[str, ...]) -> list[dict[str, Any]]:
        lowered = {interest.lower() for interest in interests}
        ranked = sorted(
            attractions,
            key=lambda item: sum(str(tag).lower() in lowered for tag in item.get("tags", [])),
            reverse=True,
        )
        return ranked or attractions

    def _build_itinerary(
        self,
        days: int,
        attractions: list[dict[str, Any]],
        restaurants: list[dict[str, Any]],
        daily_cost: dict[str, int],
    ) -> tuple[list[str], list[int]]:
        rows: list[str] = []
        totals: list[int] = []
        for day in range(days):
            morning = attractions[(day * 2) % len(attractions)]
            afternoon = attractions[(day * 2 + 1) % len(attractions)]
            restaurant = restaurants[day % len(restaurants)]
            total = int(daily_cost["lodging_cny"]) + int(daily_cost["food_cny"]) + int(daily_cost["local_transport_cny"]) + int(morning["ticket_cny"]) + int(afternoon["ticket_cny"])
            totals.append(total)
            rows.append(
                f"| 第 {day + 1} 天 | {morning['name']}（¥{morning['ticket_cny']}） | {afternoon['name']}（¥{afternoon['ticket_cny']}） | {restaurant['name']} · {restaurant['cuisine']}（约 ¥{restaurant['avg_cost_cny']}） | ¥{total} |"
            )
        return rows, totals

    def _budget_line(self, budget: int | None, total: int) -> str:
        if budget is None:
            return "未设置预算上限；可按住宿档位和交通方式调整。"
        difference = budget - total
        if difference >= 0:
            return f"预算 ¥{budget}，预计结余 ¥{difference}。"
        return f"预算 ¥{budget}，预计超出 ¥{-difference}；优先降低住宿档位或缩短天数。"
