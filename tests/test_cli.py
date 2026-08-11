from __future__ import annotations

from typer.testing import CliRunner

from tool_agent.cli import app


def test_cli_exposes_run_subcommand() -> None:
    result = CliRunner().invoke(app, ["run", "从知识库解释 LangGraph", "--offline"])

    assert result.exit_code == 0
    assert "Trace" in result.output
    assert "Final Answer" in result.output
