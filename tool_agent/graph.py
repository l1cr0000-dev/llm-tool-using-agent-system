from __future__ import annotations

from functools import partial
from typing import Any

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from tool_agent.llm import LLMClient, create_default_llm
from tool_agent.nodes import (
    decide_after_execute,
    decide_after_route,
    execute_selected_tool,
    plan_task,
    recover_failed_step,
    route_next_step,
    synthesize_answer,
)
from tool_agent.state import AgentStateDict
from tool_agent.tools.registry import ToolRegistry


def build_graph(llm_client: LLMClient | None = None, tool_registry: ToolRegistry | None = None):
    """组装 LangGraph 状态机。

    面试讲法：
    - LangGraph 的每个 node 都是一个函数，输入/输出都是同一个 state。
    - 这里把 Agent 拆成 planner、router、execute_tool、recover、synthesizer。
    - 这样复杂任务不是一次 prompt 结束，而是由图结构控制多步执行。
    """
    llm = llm_client or create_default_llm()
    registry = tool_registry or ToolRegistry()
    builder = StateGraph(AgentStateDict)

    # partial 用来把外部依赖注入 node。这样测试时可以换成 FakeLLM/FakeTools，
    # 真实运行时再使用 DeepSeek 和真实工具。
    builder.add_node("planner", partial(plan_task, llm_client=llm))
    builder.add_node("router", route_next_step)
    builder.add_node("execute_tool", partial(execute_selected_tool, tool_registry=registry))
    builder.add_node("recover", recover_failed_step)
    builder.add_node("synthesizer", partial(synthesize_answer, llm_client=llm))

    # 固定流程：先规划，再路由。之后是否执行工具、恢复、或结束，由条件边决定。
    builder.add_edge(START, "planner")
    builder.add_edge("planner", "router")
    builder.add_conditional_edges("router", decide_after_route, {"execute_tool": "execute_tool", "synthesizer": "synthesizer"})
    builder.add_conditional_edges(
        "execute_tool",
        decide_after_execute,
        {"router": "router", "recover": "recover", "synthesizer": "synthesizer"},
    )
    builder.add_edge("recover", "execute_tool")
    builder.add_edge("synthesizer", END)

    # InMemorySaver 是 LangGraph 的 checkpoint。这里用于本地 demo；
    # 如果要做生产持久化，可以替换成 Redis/Postgres checkpoint saver。
    return builder.compile(checkpointer=InMemorySaver())


def initial_state(question: str) -> AgentStateDict:
    """创建一次任务的初始状态。

    state 是这个项目的核心：所有跨步骤信息都显式放在这里，而不是藏在聊天历史里。
    """
    return {
        "question": question,
        "plan": [],
        "current_step": 0,
        "selected_tool": None,
        "tool_input": None,
        "tool_results": [],
        "working_memory": [],
        "retry_count": 0,
        "next_action": None,
        "final_answer": None,
        "trace": [],
    }


def run_agent(question: str, graph=None, thread_id: str = "default") -> dict[str, Any]:
    """一次性执行完整 graph，适合普通 CLI 输出。"""
    app = graph or build_graph()
    config = {"configurable": {"thread_id": thread_id}}
    return app.invoke(initial_state(question), config=config)


def stream_agent(question: str, graph=None, thread_id: str = "default"):
    """逐节点输出 graph 更新，适合调试和演示 Agent trace。"""
    app = graph or build_graph()
    config = {"configurable": {"thread_id": thread_id}}
    yield from app.stream(initial_state(question), config=config)
