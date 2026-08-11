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
    travelers: int = 1
    lodging_preference: str = "舒适"
    pace: str = "适中"

    def validate(self) -> None:
        if not self.origin.strip() or not self.destination.strip():
            raise ValueError("origin and destination are required")
        if not 1 <= self.days <= 14:
            raise ValueError("days must be between 1 and 14")
        if self.budget_cny is not None and self.budget_cny <= 0:
            raise ValueError("budget must be a positive amount")
        if not 1 <= self.travelers <= 12:
            raise ValueError("travelers must be between 1 and 12")
        if self.lodging_preference not in {"经济", "舒适", "高端"}:
            raise ValueError("lodging preference must be 经济, 舒适, or 高端")
        if self.pace not in {"轻松", "适中", "充实"}:
            raise ValueError("pace must be 轻松, 适中, or 充实")


@dataclass(frozen=True, slots=True)
class TravelPlanResult:
    """A machine-readable travel plan suitable for CLI, APIs, and persistence."""

    markdown: str
    complete: bool
    total_cost_cny: int | None
    transport_cost_cny: int | None
    daily_costs_cny: tuple[int, ...]
    warnings: tuple[str, ...]
    trace: tuple[str, ...]
    tool_results: tuple[dict[str, Any], ...]
    details: dict[str, Any]


class TravelPlanner:
    """Uses the existing agent to collect facts, then renders a traceable itinerary."""

    def __init__(self, agent_runner: Callable[[str], dict[str, Any]] | None = None, graph=None) -> None:
        self._graph = graph
        self._agent_runner = agent_runner

    def create_plan(self, request: TravelRequest) -> str:
        return self.create_plan_result(request).markdown

    def create_plan_result(self, request: TravelRequest) -> TravelPlanResult:
        request.validate()
        result = self._run_agent(request)
        data = self._tool_data(result)
        transport = data.get("transport_quote")
        guide = data.get("destination_guide")
        if not transport or not guide:
            missing = "、".join(name for name, value in {"交通报价": transport, "目的地指南": guide}.items() if not value)
            return TravelPlanResult(
                markdown=f"# {request.destination} {request.days} 日旅行计划\n\n暂无法生成完整计划，缺少：{missing}。请配置联网搜索或选择内置目的地。",
                complete=False,
                total_cost_cny=None,
                transport_cost_cny=None,
                daily_costs_cny=(),
                warnings=(f"缺少：{missing}",),
                trace=tuple(result.get("trace", [])),
                tool_results=tuple(result.get("tool_results", [])),
                details={},
            )

        attractions = self._rank_attractions(guide["attractions"], request.interests)
        restaurants = guide["restaurants"]
        drinks = guide.get("drinks", []) or [{"name": "本地咖啡馆", "area": "市中心", "kind": "咖啡", "avg_cost_cny": 35}]
        daily_cost = guide["daily_cost"]
        stay = self._select_stay(guide.get("accommodations", []), request, daily_cost)
        local_transport = guide.get("local_transport", [])
        itinerary, daily_totals, daily_details = self._build_itinerary(
            request.days, attractions, restaurants, drinks, daily_cost, stay, local_transport, request.pace
        )
        transport_cost = int(transport["recommended"]["cost_cny"]) * 2
        total = transport_cost + sum(daily_totals)
        group_total = total * request.travelers
        budget_line = self._budget_line(request.budget_cny, total)
        options = "；".join(
            f"{item['mode']}：约 {item['duration_hours']} 小时 / ¥{item['cost_cny']}（单程）"
            for item in transport["options"]
        )
        interests = "、".join(request.interests) if request.interests else "综合体验"
        warnings = (
            "景点票价、餐厅排队和交通价格会随日期变化；出发前请以官方渠道和实际订单为准。",
            "需要实时航班、酒店或天气时，在请求中加入“最新”，并配置 `TAVILY_API_KEY` 让 Agent 补充联网搜索。",
        )
        markdown = "\n".join(
            [
                f"# {request.destination} {request.days} 日旅行计划",
                "",
                f"> 出发地：{request.origin} ｜ {request.travelers} 人出行 ｜ 节奏：{request.pace} ｜ 偏好：{interests} ｜ 费用均为单人估算（人民币）",
                "",
                "## 往返交通",
                f"- 推荐：{transport['recommended']['mode']}，单程约 {transport['recommended']['duration_hours']} 小时，¥{transport['recommended']['cost_cny']}；往返预计 ¥{transport_cost}。",
                f"- 备选：{options}。",
                "",
                "## 住宿建议",
                f"- {stay['name']}（{stay['area']} · {stay['style']}）：约 ¥{stay['avg_cost_cny']} / 人 / 晚；{stay.get('note', '优先选择交通便利、可灵活取消的房型。')}",
                "",
                "## 吃喝建议",
                *(f"- {item['name']}（{item.get('area', '推荐区域')} · {item['cuisine']}）：人均约 ¥{item['avg_cost_cny']}。" for item in restaurants),
                *(f"- {item['name']}（{item.get('area', '推荐区域')} · {item['kind']}）：人均约 ¥{item['avg_cost_cny']}。" for item in drinks),
                "",
                "## 本地出行",
                *(f"- {item['mode']}：{item['tip']}（日均约 ¥{item['avg_cost_cny']}）。" for item in local_transport),
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
                f"- {request.travelers} 人合计：¥{group_total}",
                f"- {budget_line}",
                "",
                "## 预订清单",
                "- [ ] 先锁定往返交通与到达时间，避免影响首日行程。",
                "- [ ] 预订可取消住宿，并确认入住 / 退房时间。",
                "- [ ] 提前预约热门景点与餐厅，保留电子凭证。",
                "- [ ] 出发前 48 小时复查天气、交通变动和营业时间。",
                "",
                "## 预订建议",
                *(f"- {warning}" for warning in warnings),
            ]
        )
        return TravelPlanResult(
            markdown=markdown,
            complete=True,
            total_cost_cny=total,
            transport_cost_cny=transport_cost,
            daily_costs_cny=tuple(daily_totals),
            warnings=warnings,
            trace=tuple(result.get("trace", [])),
            tool_results=tuple(result.get("tool_results", [])),
            details={
                "transport": transport,
                "stay": stay,
                "food": restaurants,
                "drinks": drinks,
                "local_transport": local_transport,
                "itinerary": daily_details,
                "budget": {
                    "per_person_cny": total,
                    "group_total_cny": group_total,
                    "transport_cny": transport_cost,
                    "daily_costs_cny": daily_totals,
                    "travelers": request.travelers,
                },
                "booking_checklist": [
                    "锁定往返交通与到达时间",
                    "预订可取消住宿并确认入住时间",
                    "预约热门景点与餐厅",
                    "出发前 48 小时复查天气和营业时间",
                ],
            },
        )

    def _run_agent(self, request: TravelRequest) -> dict[str, Any]:
        question = (
            f"旅游计划；出发地: {request.origin}；目的地: {request.destination}；"
            f"天数: {request.days}；预算: {request.budget_cny or '未设置'}；"
            f"人数: {request.travelers}；住宿: {request.lodging_preference}；节奏: {request.pace}；"
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

    def _select_stay(
        self, accommodations: list[dict[str, Any]], request: TravelRequest, daily_cost: dict[str, int]
    ) -> dict[str, Any]:
        if not accommodations:
            return {
                "name": f"{request.destination}市中心住宿",
                "area": "市中心",
                "style": request.lodging_preference,
                "avg_cost_cny": int(daily_cost["lodging_cny"]),
                "note": "本地知识库暂无具体住宿，建议选择交通便利且可取消的房型。",
            }
        return max(
            accommodations,
            key=lambda item: int(str(item.get("style", "")) == request.lodging_preference),
        )

    def _build_itinerary(
        self,
        days: int,
        attractions: list[dict[str, Any]],
        restaurants: list[dict[str, Any]],
        drinks: list[dict[str, Any]],
        daily_cost: dict[str, int],
        stay: dict[str, Any],
        local_transport: list[dict[str, Any]],
        pace: str,
    ) -> tuple[list[str], list[int], list[dict[str, Any]]]:
        rows: list[str] = []
        totals: list[int] = []
        details: list[dict[str, Any]] = []
        for day in range(days):
            morning = attractions[(day * 2) % len(attractions)]
            afternoon = attractions[(day * 2 + 1) % len(attractions)]
            restaurant = restaurants[day % len(restaurants)]
            drink = drinks[day % len(drinks)]
            mobility = local_transport[day % len(local_transport)] if local_transport else {"mode": "步行 + 公共交通", "tip": "优先选择同一区域景点", "avg_cost_cny": daily_cost["local_transport_cny"]}
            total = int(stay["avg_cost_cny"]) + int(daily_cost["food_cny"]) + int(mobility["avg_cost_cny"]) + int(morning["ticket_cny"]) + int(afternoon["ticket_cny"])
            totals.append(total)
            rows.append(
                f"| 第 {day + 1} 天 | {morning['name']}（¥{morning['ticket_cny']}） | {afternoon['name']}（¥{afternoon['ticket_cny']}） | {restaurant['name']} · {restaurant['cuisine']}（约 ¥{restaurant['avg_cost_cny']}） | ¥{total} |"
            )
            details.append(
                {
                    "day": day + 1,
                    "pace": pace,
                    "morning": morning,
                    "afternoon": afternoon,
                    "restaurant": restaurant,
                    "drink": drink,
                    "local_transport": mobility,
                    "estimated_cost_cny": total,
                }
            )
        return rows, totals, details

    def _budget_line(self, budget: int | None, total: int) -> str:
        if budget is None:
            return "未设置预算上限；可按住宿档位和交通方式调整。"
        difference = budget - total
        if difference >= 0:
            return f"预算 ¥{budget}，预计结余 ¥{difference}。"
        return f"预算 ¥{budget}，预计超出 ¥{-difference}；优先降低住宿档位或缩短天数。"
