"""Reproducible evaluation helpers for the code-based agent and Dify workflow.

The module deliberately keeps the comparison data format framework-neutral.  The
same JSON schema can capture a LangGraph run or a manually exported Dify run,
so the report compares observed behavior instead of implementation details.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Iterable


@dataclass(frozen=True, slots=True)
class EvaluationCase:
    """A test task with the tools required to solve it correctly."""

    case_id: str
    question: str
    expected_tools: tuple[str, ...]
    min_steps: int

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "EvaluationCase":
        return cls(
            case_id=str(value["case_id"]),
            question=str(value["question"]),
            expected_tools=tuple(str(tool) for tool in value["expected_tools"]),
            min_steps=int(value.get("min_steps", len(value["expected_tools"]))),
        )


@dataclass(frozen=True, slots=True)
class CostModel:
    """Transparent unit-cost model for comparisons without provider billing data."""

    planner_and_synthesis_usd: float = 0.0018
    tool_call_usd: dict[str, float] | None = None

    def estimate(self, tools: Iterable[str]) -> float:
        prices = self.tool_call_usd or {
            "web_search": 0.0080,
            "knowledge_base": 0.0002,
            "calculator": 0.0,
            "get_time": 0.0,
            "get_weather": 0.0,
        }
        return round(self.planner_and_synthesis_usd + sum(prices.get(tool, 0.0) for tool in tools), 6)


@dataclass(frozen=True, slots=True)
class EvaluationRecord:
    """One normalized workflow run, serializable to JSON for later comparison."""

    case_id: str
    planned_tools: tuple[str, ...]
    executed_tools: tuple[str, ...]
    task_decomposition_score: float
    tool_selection_f1: float
    execution_stability: float
    estimated_cost_usd: float
    error_categories: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_cases(path: str | Path) -> list[EvaluationCase]:
    """Load the small, version-controlled benchmark set."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("evaluation cases must be a JSON array")
    return [EvaluationCase.from_dict(item) for item in raw]


def evaluate_pipeline(
    cases: Iterable[EvaluationCase],
    agent_runner: Callable[[str], dict[str, Any]],
    cost_model: CostModel | None = None,
) -> list[EvaluationRecord]:
    """Run benchmark cases through the agent and normalize their measurements."""
    model = cost_model or CostModel()
    records: list[EvaluationRecord] = []
    for case in cases:
        result = agent_runner(case.question)
        planned_tools = tuple(
            str(step["tool"])
            for step in result.get("plan", [])
            if str(step.get("tool")) != "synthesize"
        )
        tool_results = result.get("tool_results", [])
        executed_tools = tuple(str(item.get("tool")) for item in tool_results)
        successful_calls = sum(bool(item.get("ok")) for item in tool_results)
        stability = successful_calls / len(tool_results) if tool_results else 0.0
        records.append(
            EvaluationRecord(
                case_id=case.case_id,
                planned_tools=planned_tools,
                executed_tools=executed_tools,
                task_decomposition_score=_decomposition_score(planned_tools, case.min_steps),
                tool_selection_f1=_tool_f1(planned_tools, case.expected_tools),
                execution_stability=round(stability, 4),
                estimated_cost_usd=model.estimate(executed_tools),
                error_categories=tuple(_classify_error(item.get("error")) for item in tool_results if not item.get("ok")),
            )
        )
    return records


def load_dify_records(path: str | Path) -> list[EvaluationRecord]:
    """Load normalized observations exported or manually recorded from Dify.

    Dify does not expose identical trace fields across versions, so the template
    asks for the four evaluated metrics directly.  This avoids invented parity.
    """
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = raw.get("runs") if isinstance(raw, dict) else raw
    if not isinstance(rows, list):
        raise ValueError("Dify results must be an array or an object with a 'runs' array")
    records: list[EvaluationRecord] = []
    for row in rows:
        required = {
            "case_id",
            "task_decomposition_score",
            "tool_selection_f1",
            "execution_stability",
            "estimated_cost_usd",
        }
        missing = required.difference(row)
        if missing:
            raise ValueError(f"Dify result is missing: {', '.join(sorted(missing))}")
        records.append(
            EvaluationRecord(
                case_id=str(row["case_id"]),
                planned_tools=tuple(str(value) for value in row.get("planned_tools", [])),
                executed_tools=tuple(str(value) for value in row.get("executed_tools", [])),
                task_decomposition_score=float(row["task_decomposition_score"]),
                tool_selection_f1=float(row["tool_selection_f1"]),
                execution_stability=float(row["execution_stability"]),
                estimated_cost_usd=float(row["estimated_cost_usd"]),
                error_categories=tuple(str(value) for value in row.get("error_categories", [])),
            )
        )
    return records


def build_report(pipeline_records: list[EvaluationRecord], dify_records: list[EvaluationRecord] | None = None) -> dict[str, Any]:
    """Build a JSON-safe report with aggregate metrics and actionable error groups."""
    report: dict[str, Any] = {
        "agent_pipeline": _summary(pipeline_records),
        "agent_pipeline_error_analysis": _error_analysis(pipeline_records),
        "records": [record.to_dict() for record in pipeline_records],
    }
    if dify_records is not None:
        report["dify_workflow"] = _summary(dify_records)
        report["dify_error_analysis"] = _error_analysis(dify_records)
        report["comparison"] = _comparison(report["agent_pipeline"], report["dify_workflow"])
    return report


def _decomposition_score(planned_tools: tuple[str, ...], min_steps: int) -> float:
    """Score whether planning produced an appropriately sized executable plan."""
    if min_steps <= 0:
        return 1.0
    return round(min(len(planned_tools), min_steps) / max(len(planned_tools), min_steps), 4)


def _tool_f1(actual: tuple[str, ...], expected: tuple[str, ...]) -> float:
    """Multiset F1 rewards selecting required tools while penalizing extra tools."""
    if not actual or not expected:
        return 0.0
    overlap = sum((Counter(actual) & Counter(expected)).values())
    precision = overlap / len(actual)
    recall = overlap / len(expected)
    return round(2 * precision * recall / (precision + recall), 4) if precision + recall else 0.0


def _classify_error(error: Any) -> str:
    message = str(error or "").lower()
    if "api_key" in message or "not configured" in message:
        return "configuration"
    if "timeout" in message or "connection" in message or "http" in message:
        return "external_dependency"
    if "no matching" in message or "no results" in message:
        return "retrieval_miss"
    if "unknown tool" in message:
        return "routing"
    return "tool_execution"


def _summary(records: list[EvaluationRecord]) -> dict[str, float | int]:
    if not records:
        return {"runs": 0, "task_decomposition_score": 0.0, "tool_selection_f1": 0.0, "execution_stability": 0.0, "estimated_cost_usd": 0.0}
    size = len(records)
    return {
        "runs": size,
        "task_decomposition_score": round(sum(item.task_decomposition_score for item in records) / size, 4),
        "tool_selection_f1": round(sum(item.tool_selection_f1 for item in records) / size, 4),
        "execution_stability": round(sum(item.execution_stability for item in records) / size, 4),
        "estimated_cost_usd": round(sum(item.estimated_cost_usd for item in records), 6),
    }


def _error_analysis(records: list[EvaluationRecord]) -> dict[str, Any]:
    cases_by_error: dict[str, list[str]] = defaultdict(list)
    calls_by_error: Counter[str] = Counter()
    for record in records:
        for category in record.error_categories:
            calls_by_error[category] += 1
            if record.case_id not in cases_by_error[category]:
                cases_by_error[category].append(record.case_id)
    recommendations = {
        "configuration": "Validate API-key availability before running the benchmark.",
        "external_dependency": "Retry with backoff and retain a local fallback tool.",
        "retrieval_miss": "Expand the knowledge base or improve chunking and query rewriting.",
        "routing": "Constrain planner output and add tool-schema validation.",
        "tool_execution": "Add a tool-specific guardrail or input validator.",
    }
    return {
        category: {
            "failed_calls": calls_by_error[category],
            "case_ids": case_ids,
            "recommended_action": recommendations[category],
        }
        for category, case_ids in sorted(cases_by_error.items())
    }


def _comparison(pipeline: dict[str, Any], dify: dict[str, Any]) -> dict[str, float]:
    keys = ("task_decomposition_score", "tool_selection_f1", "execution_stability", "estimated_cost_usd")
    return {f"agent_minus_dify_{key}": round(float(pipeline[key]) - float(dify[key]), 6) for key in keys}
