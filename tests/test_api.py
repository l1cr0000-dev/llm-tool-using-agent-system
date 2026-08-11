from __future__ import annotations

from fastapi.testclient import TestClient

from tool_agent.api import create_app


def test_api_creates_persists_and_reads_travel_plan(tmp_path) -> None:
    app = create_app(database_path=tmp_path / "plans.db", offline=True)
    client = TestClient(app)

    health = client.get("/health")
    created = client.post(
        "/api/travel-plans",
        json={
            "origin": "北京",
            "destination": "上海",
            "days": 2,
            "budget_cny": 4000,
            "interests": ["美食", "城市"],
        },
    )

    assert health.status_code == 200
    assert health.json() == {"status": "ok", "offline": True}
    assert created.status_code == 201
    record = created.json()
    assert record["result"]["complete"] is True
    assert record["result"]["total_cost_cny"] > 0
    assert "# 上海 2 日旅行计划" in record["result"]["markdown"]

    fetched = client.get(f"/api/travel-plans/{record['id']}")
    listed = client.get("/api/travel-plans?limit=5")

    assert fetched.status_code == 200
    assert fetched.json()["id"] == record["id"]
    assert [item["id"] for item in listed.json()] == [record["id"]]


def test_api_rejects_invalid_request_and_reports_missing_plan(tmp_path) -> None:
    client = TestClient(create_app(database_path=tmp_path / "plans.db", offline=True))

    invalid = client.post("/api/travel-plans", json={"origin": "", "destination": "上海"})
    missing = client.get("/api/travel-plans/not-found")

    assert invalid.status_code == 422
    assert missing.status_code == 404
