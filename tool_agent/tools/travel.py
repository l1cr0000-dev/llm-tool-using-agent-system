"""Travel-specific tools with deterministic, inspectable local data.

The destination guide is a small curated RAG corpus for offline demos.  In a
production deployment it can be replaced by a vector store or a city-content
API without changing the AgentTool interface.
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

from tool_agent.tools.base import ToolResult


class DestinationGuideTool:
    """Retrieve a destination guide containing attractions, food, and prices."""

    name = "destination_guide"

    def __init__(self, guide_path: str | Path) -> None:
        self.guide_path = Path(guide_path)

    def run(self, query: str) -> ToolResult:
        guides = self._load_guides()
        destination = self._extract_destination(query)
        guide = next((item for item in guides if self._matches_destination(item, destination)), None)
        if guide is None:
            return ToolResult(
                ok=False,
                tool=self.name,
                error=f"no local destination guide found for: {destination or query}",
            )
        return ToolResult(
            ok=True,
            tool=self.name,
            data={
                "destination": guide["city"],
                "source": self.guide_path.name,
                "attractions": guide["attractions"],
                "restaurants": guide["restaurants"],
                "accommodations": guide.get("accommodations", []),
                "drinks": guide.get("drinks", []),
                "local_transport": guide.get("local_transport", []),
                "daily_cost": guide["daily_cost"],
            },
        )

    def _load_guides(self) -> list[dict[str, Any]]:
        if not self.guide_path.exists():
            return []
        data = json.loads(self.guide_path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise ValueError("destination guide corpus must be a JSON array")
        return [item for item in data if isinstance(item, dict)]

    def _extract_destination(self, query: str) -> str:
        match = re.search(r"(?:目的地|destination)\s*[:：]\s*([^,，;；\n]+)", query, flags=re.IGNORECASE)
        return match.group(1).strip() if match else query.strip()

    def _matches_destination(self, guide: dict[str, Any], destination: str) -> bool:
        names = [str(guide.get("city", "")), *(str(alias) for alias in guide.get("aliases", []))]
        lowered = destination.lower()
        return any(name.lower() in lowered or lowered in name.lower() for name in names if name)


class TransportQuoteTool:
    """Estimate one-way per-person transport options for supported city pairs."""

    name = "transport_quote"

    _cities = {
        "北京": (39.9042, 116.4074, ("beijing",)),
        "上海": (31.2304, 121.4737, ("shanghai",)),
        "杭州": (30.2741, 120.1551, ("hangzhou",)),
        "成都": (30.5728, 104.0668, ("chengdu",)),
        "三亚": (18.2528, 109.5119, ("sanya",)),
    }

    def run(self, query: str) -> ToolResult:
        origin, destination = self._extract_route(query)
        if not origin or not destination:
            return ToolResult(ok=False, tool=self.name, error="origin and destination are required")
        resolved_origin = self._resolve_city(origin)
        resolved_destination = self._resolve_city(destination)
        if not resolved_origin or not resolved_destination:
            return ToolResult(
                ok=False,
                tool=self.name,
                error=f"no offline transport profile for route: {origin} -> {destination}",
            )
        distance = round(self._distance_km(resolved_origin, resolved_destination))
        options = self._options(distance)
        recommended = min(options, key=lambda option: option["cost_cny"] if distance < 1500 else option["duration_hours"])
        return ToolResult(
            ok=True,
            tool=self.name,
            data={
                "origin": resolved_origin,
                "destination": resolved_destination,
                "distance_km": distance,
                "options": options,
                "recommended": recommended,
                "pricing_note": "Estimated one-way per-person price; verify availability before booking.",
            },
        )

    def _extract_route(self, query: str) -> tuple[str, str]:
        origin_match = re.search(r"(?:出发地|origin)\s*[:：]\s*([^,，;；\n]+)", query, flags=re.IGNORECASE)
        destination_match = re.search(r"(?:目的地|destination)\s*[:：]\s*([^,，;；\n]+)", query, flags=re.IGNORECASE)
        return (
            origin_match.group(1).strip() if origin_match else "",
            destination_match.group(1).strip() if destination_match else "",
        )

    def _resolve_city(self, value: str) -> str | None:
        lowered = value.lower()
        for city, (_, _, aliases) in self._cities.items():
            if city in value or any(alias in lowered for alias in aliases):
                return city
        return None

    def _distance_km(self, origin: str, destination: str) -> float:
        lat_a, lon_a, _ = self._cities[origin]
        lat_b, lon_b, _ = self._cities[destination]
        radius = 6371.0
        phi_a, phi_b = math.radians(lat_a), math.radians(lat_b)
        delta_phi, delta_lambda = math.radians(lat_b - lat_a), math.radians(lon_b - lon_a)
        haversine = math.sin(delta_phi / 2) ** 2 + math.cos(phi_a) * math.cos(phi_b) * math.sin(delta_lambda / 2) ** 2
        return 2 * radius * math.asin(math.sqrt(haversine))

    def _options(self, distance_km: int) -> list[dict[str, int | str]]:
        train = {"mode": "高铁二等座", "duration_hours": max(1, round(distance_km / 250)), "cost_cny": max(120, round(distance_km * 0.46))}
        flight = {"mode": "经济舱", "duration_hours": max(2, round(distance_km / 700) + 2), "cost_cny": max(480, round(distance_km * 0.78))}
        return [train, flight] if distance_km <= 2000 else [flight, train]
