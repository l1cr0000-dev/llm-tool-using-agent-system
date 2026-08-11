"""REST API for embedding the travel-planning agent in a real application."""

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable

from fastapi import FastAPI, HTTPException, Query, status
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from tool_agent.graph import build_graph
from tool_agent.llm import HeuristicLLMClient
from tool_agent.tools.registry import ToolRegistry
from tool_agent.travel import TravelPlanResult, TravelPlanner, TravelRequest


class TravelPlanInput(BaseModel):
    """Public request contract for programmatic clients."""

    origin: str = Field(min_length=1, max_length=80)
    destination: str = Field(min_length=1, max_length=80)
    days: int = Field(default=3, ge=1, le=14)
    budget_cny: int | None = Field(default=None, ge=1)
    interests: list[str] = Field(default_factory=list, max_length=8)
    travelers: int = Field(default=1, ge=1, le=12)
    lodging_preference: str = Field(default="舒适", pattern="^(经济|舒适|高端)$")
    pace: str = Field(default="适中", pattern="^(轻松|适中|充实)$")


class TravelPlanRepository:
    """Small SQLite repository; each operation owns its connection for web safety."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS travel_plans (
                    id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    request_json TEXT NOT NULL,
                    result_json TEXT NOT NULL
                )
                """
            )
            connection.execute("CREATE INDEX IF NOT EXISTS idx_travel_plans_created_at ON travel_plans (created_at DESC)")
            connection.execute("PRAGMA optimize")

    def save(self, request: TravelPlanInput, result: TravelPlanResult) -> dict[str, object]:
        record = {
            "id": str(uuid.uuid4()),
            "created_at": datetime.now(UTC).isoformat(),
            "request": request.model_dump(),
            "result": asdict(result),
        }
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO travel_plans (id, created_at, request_json, result_json) VALUES (?, ?, ?, ?)",
                (
                    record["id"],
                    record["created_at"],
                    json.dumps(record["request"], ensure_ascii=False),
                    json.dumps(record["result"], ensure_ascii=False),
                ),
            )
        return record

    def get(self, plan_id: str) -> dict[str, object] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT id, created_at, request_json, result_json FROM travel_plans WHERE id = ?", (plan_id,)
            ).fetchone()
        return self._record_from_row(row) if row else None

    def list(self, limit: int) -> list[dict[str, object]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id, created_at, request_json, result_json FROM travel_plans ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._record_from_row(row) for row in rows]

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.database_path)

    def _record_from_row(self, row: tuple[str, str, str, str]) -> dict[str, object]:
        return {
            "id": row[0],
            "created_at": row[1],
            "request": json.loads(row[2]),
            "result": json.loads(row[3]),
        }


def create_app(
    database_path: str | Path = "data/travel_plans.db",
    offline: bool = True,
    planner_factory: Callable[[bool], TravelPlanner] | None = None,
) -> FastAPI:
    """Create the API app. Offline is the safe default for local demos and tests."""
    repository = TravelPlanRepository(database_path)
    make_planner = planner_factory or _default_planner
    app = FastAPI(
        title="Travel Planner Agent API",
        version="0.3.0",
        description="Generate, persist, and inspect complete tool-using travel plans. OpenAPI is available at /docs.",
    )
    web_dir = Path(__file__).resolve().parent / "web"
    app.mount("/static", StaticFiles(directory=web_dir), name="static")

    @app.get("/", include_in_schema=False)
    def home() -> FileResponse:
        return FileResponse(web_dir / "index.html")

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon() -> Response:
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @app.get("/health")
    def health() -> dict[str, str | bool]:
        return {"status": "ok", "offline": offline}

    @app.post("/api/travel-plans", status_code=status.HTTP_201_CREATED)
    def create_travel_plan(payload: TravelPlanInput) -> dict[str, object]:
        request = TravelRequest(
            origin=payload.origin,
            destination=payload.destination,
            days=payload.days,
            budget_cny=payload.budget_cny,
            interests=tuple(payload.interests),
            travelers=payload.travelers,
            lodging_preference=payload.lodging_preference,
            pace=payload.pace,
        )
        result = make_planner(offline).create_plan_result(request)
        return repository.save(payload, result)

    @app.get("/api/travel-plans")
    def list_travel_plans(limit: int = Query(default=20, ge=1, le=100)) -> list[dict[str, object]]:
        return repository.list(limit)

    @app.get("/api/travel-plans/{plan_id}")
    def get_travel_plan(plan_id: str) -> dict[str, object]:
        record = repository.get(plan_id)
        if record is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="travel plan not found")
        return record

    return app


def _default_planner(offline: bool) -> TravelPlanner:
    if not offline:
        return TravelPlanner()
    graph = build_graph(
        llm_client=HeuristicLLMClient(),
        tool_registry=ToolRegistry(allow_external_tools=False),
    )
    return TravelPlanner(graph=graph)
