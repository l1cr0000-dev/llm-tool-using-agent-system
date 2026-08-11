from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Annotated

import typer
from dotenv import load_dotenv

from tool_agent.graph import build_graph, run_agent, stream_agent
from tool_agent.evaluation import build_report, evaluate_pipeline, load_cases, load_dify_records
from tool_agent.llm import HeuristicLLMClient
from tool_agent.tools.registry import ToolRegistry

app = typer.Typer(help="Run the LangGraph LLM tool-using agent.")


@app.callback()
def main() -> None:
    """LLM tool-using agent CLI."""


@app.command()
def run(
    question: Annotated[str, typer.Argument(help="User task or question.")],
    stream: Annotated[bool, typer.Option("--stream", help="Print graph node updates as they happen.")] = False,
    offline: Annotated[bool, typer.Option(help="Use the deterministic planner and disable web search credentials.")] = False,
) -> None:
    # 从本地 .env 读取 DeepSeek/Tavily key。这个文件被 .gitignore 忽略，不应该提交。
    load_dotenv()

    # 每次 CLI 运行使用独立 thread_id，避免 LangGraph checkpoint 状态串到别的任务。
    thread_id = str(uuid.uuid4())
    graph = _build_graph(offline)
    if stream:
        # stream 模式按 node 输出更新，适合展示 LangGraph 每一步 state 如何变化。
        for event in stream_agent(question, graph=graph, thread_id=thread_id):
            for node_name, update in event.items():
                typer.echo(f"\n[{node_name}]")
                typer.echo(json.dumps(update, ensure_ascii=False, indent=2, default=str))
        return

    result = run_agent(question, graph=graph, thread_id=thread_id)
    # 普通模式输出三块：执行轨迹、工具结果、最终答案。
    typer.echo("\nTrace")
    typer.echo("-----")
    for item in result.get("trace", []):
        typer.echo(f"- {item}")

    typer.echo("\nTool Results")
    typer.echo("------------")
    for item in result.get("tool_results", []):
        typer.echo(json.dumps(item, ensure_ascii=False, indent=2, default=str))

    typer.echo("\nFinal Answer")
    typer.echo("------------")
    typer.echo(result.get("final_answer") or "")


@app.command()
def evaluate(
    cases: Annotated[Path, typer.Option(help="Path to the version-controlled benchmark cases.")] = Path("evaluation/cases.json"),
    dify_results: Annotated[Path | None, typer.Option(help="Optional normalized Dify observations JSON.")] = None,
    output: Annotated[Path | None, typer.Option(help="Optional path to save the JSON report.")] = None,
    offline: Annotated[bool, typer.Option(help="Use the deterministic planner and disable web search credentials.")] = False,
) -> None:
    """Evaluate the code pipeline and optionally compare it with Dify observations."""
    load_dotenv()
    graph = _build_graph(offline)
    pipeline_records = evaluate_pipeline(
        load_cases(cases),
        lambda question: run_agent(question, graph=graph, thread_id=str(uuid.uuid4())),
    )
    dify_records = load_dify_records(dify_results) if dify_results else None
    report = build_report(pipeline_records, dify_records)
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(payload + "\n", encoding="utf-8")
        typer.echo(f"Saved evaluation report to {output}")
    typer.echo(payload)


def _build_graph(offline: bool):
    """Build an offline-safe graph for demos and deterministic test runs."""
    if not offline:
        return None
    return build_graph(
        llm_client=HeuristicLLMClient(),
        tool_registry=ToolRegistry(allow_external_tools=False),
    )


if __name__ == "__main__":
    app()
