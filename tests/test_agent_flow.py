from __future__ import annotations

from tool_agent.graph import build_graph, run_agent
from tool_agent.llm import DeepSeekLLMClient, FakeLLMClient
from tool_agent.nodes import route_next_step
from tool_agent.state import AgentState, PlanStep
from tool_agent.tools.base import ToolResult


def test_router_selects_weather_for_weather_step() -> None:
    state = AgentState(
        question="北京现在天气怎么样？",
        plan=[PlanStep(id=1, objective="查询北京当前天气", tool="get_weather")],
    )

    update = route_next_step(state)

    assert update["selected_tool"] == "get_weather"
    assert update["tool_input"] == "查询北京当前天气"


def test_recovery_rewrites_failed_query_and_uses_fallback_after_retry() -> None:
    from tool_agent.nodes import recover_failed_step

    state = AgentState(
        question="查询 LangGraph",
        plan=[PlanStep(id=1, objective="查询 LangGraph", tool="web_search")],
        selected_tool="web_search",
        tool_input="查询 LangGraph",
        retry_count=0,
    )

    first = recover_failed_step(state)
    assert first["retry_count"] == 1
    assert first["tool_input"] == "查询 LangGraph latest reliable source"
    assert first["next_action"] == "retry"

    state.retry_count = 1
    second = recover_failed_step(state)
    assert second["selected_tool"] == "knowledge_base"
    assert second["next_action"] == "retry"


def test_graph_runs_full_plan_with_fake_tools() -> None:
    class FakeTools:
        def run(self, name: str, query: str) -> ToolResult:
            if name == "get_time":
                return ToolResult(ok=True, tool=name, data={"current_time": "2026-07-05 15:30:00 CST+0800"})
            if name == "get_weather":
                return ToolResult(ok=True, tool=name, data={"condition": "Mainly clear", "temperature": "31 °C"})
            return ToolResult(ok=True, tool=name, data={"result": query})

    llm = FakeLLMClient(
        plan=[
            {"id": 1, "objective": "获取北京当前时间", "tool": "get_time"},
            {"id": 2, "objective": "获取北京当前天气", "tool": "get_weather"},
            {"id": 3, "objective": "综合判断是否适合户外跑步", "tool": "synthesize"},
        ],
        answer="北京当前天气晴朗，时间为下午，适合轻量户外跑步。",
    )

    graph = build_graph(llm_client=llm, tool_registry=FakeTools())
    result = run_agent("查询北京当前天气，并结合当地时间判断是否适合户外跑步", graph=graph)

    assert result["final_answer"] == "北京当前天气晴朗，时间为下午，适合轻量户外跑步。"
    assert [entry["tool"] for entry in result["tool_results"]] == ["get_time", "get_weather"]
    assert any("planner" in item for item in result["trace"])


def test_graph_stops_recovering_after_retry_budget_is_exhausted() -> None:
    class FailingTools:
        def run(self, name: str, query: str) -> ToolResult:
            return ToolResult(ok=False, tool=name, error="forced failure")

    llm = FakeLLMClient(
        plan=[
            {"id": 1, "objective": "搜索最新资料", "tool": "web_search"},
            {"id": 2, "objective": "综合已有信息", "tool": "synthesize"},
        ],
        answer="未能取得外部资料，因此基于失败状态回答。",
    )

    graph = build_graph(llm_client=llm, tool_registry=FailingTools())
    result = run_agent("搜索最新资料", graph=graph)

    assert result["final_answer"] == "未能取得外部资料，因此基于失败状态回答。"
    assert len(result["tool_results"]) == 3
    assert any("recovery budget exhausted" in item for item in result["trace"])


def test_deepseek_planner_uses_function_calling_and_normalises_plan() -> None:
    class FakeCompletions:
        def __init__(self) -> None:
            self.kwargs = None

        def create(self, **kwargs):
            self.kwargs = kwargs
            function = type("Function", (), {"arguments": '{"steps": [{"objective": "计算表达式", "tool": "calculator"}]}'})()
            call = type("ToolCall", (), {"function": function})()
            message = type("Message", (), {"tool_calls": [call]})()
            choice = type("Choice", (), {"message": message})()
            return type("Response", (), {"choices": [choice]})()

    completions = FakeCompletions()
    client = type("Client", (), {"chat": type("Chat", (), {"completions": completions})()})()
    llm = DeepSeekLLMClient.__new__(DeepSeekLLMClient)
    llm.client = client
    llm.model = "deepseek-chat"

    plan = llm.plan("计算 2 + 2")

    assert completions.kwargs["tool_choice"]["function"]["name"] == "create_execution_plan"
    assert completions.kwargs["tools"][0]["function"]["parameters"]["properties"]["steps"]
    assert [(step.tool, step.objective) for step in plan] == [
        ("calculator", "计算表达式"),
        ("synthesize", "综合已有信息回答用户问题"),
    ]
