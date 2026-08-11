from __future__ import annotations

from tool_agent.evaluation import EvaluationCase, build_report, evaluate_pipeline


def test_evaluation_scores_pipeline_and_groups_errors() -> None:
    cases = [
        EvaluationCase(
            case_id="search_then_rag",
            question="Search and compare",
            expected_tools=("web_search", "knowledge_base"),
            min_steps=2,
        )
    ]

    def fake_runner(_: str) -> dict[str, object]:
        return {
            "plan": [
                {"tool": "web_search"},
                {"tool": "knowledge_base"},
                {"tool": "synthesize"},
            ],
            "tool_results": [
                {"tool": "web_search", "ok": False, "error": "TAVILY_API_KEY is not configured"},
                {"tool": "knowledge_base", "ok": True, "error": None},
            ],
        }

    records = evaluate_pipeline(cases, fake_runner)
    record = records[0]

    assert record.task_decomposition_score == 1.0
    assert record.tool_selection_f1 == 1.0
    assert record.execution_stability == 0.5
    assert record.error_categories == ("configuration",)

    report = build_report(records)
    assert report["agent_pipeline"]["runs"] == 1
    assert report["agent_pipeline_error_analysis"]["configuration"]["case_ids"] == ["search_then_rag"]
    assert report["agent_pipeline_error_analysis"]["configuration"]["failed_calls"] == 1
