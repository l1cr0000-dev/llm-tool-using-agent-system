from __future__ import annotations

from typing import Any

from tool_agent.llm import LLMClient
from tool_agent.memory import append_memory
from tool_agent.state import AgentState, AgentStateDict, PlanStep, append_trace, get_plan, get_value
from tool_agent.tools.registry import ToolRegistry


def plan_task(state: AgentStateDict, llm_client: LLMClient) -> dict[str, Any]:
    """Planner node：让 LLM 把用户问题拆成多个可执行步骤。"""
    question = get_value(state, "question", "")
    plan = llm_client.plan(question)
    return {
        "plan": [step.to_dict() for step in plan],
        "current_step": 0,
        "trace": append_trace(state, f"planner: created {len(plan)} steps"),
    }


def route_next_step(state: AgentState | AgentStateDict) -> dict[str, Any]:
    """Router node：读取当前 plan step，决定下一步应该调用哪个工具。"""
    plan = get_plan(state)
    current = int(get_value(state, "current_step", 0))
    if current >= len(plan):
        # 防御性兜底：如果 plan 被执行完了，就直接进入 synthesis。
        return {
            "selected_tool": "synthesize",
            "tool_input": get_value(state, "question", ""),
            "next_action": "synthesize",
            "trace": append_trace(state, "router: all steps complete"),
        }
    step = plan[current]
    return {
        "selected_tool": step.tool,
        "tool_input": step.objective,
        # synthesize 是一个特殊的“结束步骤”，不需要工具执行。
        "next_action": "synthesize" if step.tool == "synthesize" else "execute",
        "trace": append_trace(state, f"router: step {step.id} -> {step.tool}"),
    }


def execute_selected_tool(state: AgentStateDict, tool_registry: ToolRegistry) -> dict[str, Any]:
    """Tool execution node：执行工具，并把结果写入 tool_results 和 working_memory。"""
    selected_tool = get_value(state, "selected_tool")
    tool_input = get_value(state, "tool_input", "")
    plan = get_plan(state)
    current = int(get_value(state, "current_step", 0))
    step = plan[current] if current < len(plan) else PlanStep(id=current + 1, objective=tool_input, tool=selected_tool)

    result = tool_registry.run(str(selected_tool), str(tool_input))

    # tool_results 偏向“给人看”和 CLI 展示；working_memory 偏向“给后续节点/LLM 用”。
    # 两者都保留，是为了可观测性和推理上下文分开。
    tool_entry = {
        "step_id": step.id,
        "objective": step.objective,
        **result.to_memory(),
    }
    update = {
        "tool_results": [*get_value(state, "tool_results", []), tool_entry],
        "working_memory": append_memory(get_value(state, "working_memory", []), step.id, step.objective, result),
        "trace": append_trace(state, f"execute: {selected_tool} ok={result.ok}"),
    }
    if result.ok:
        update["current_step"] = current + 1
        update["retry_count"] = 0
        update["next_action"] = "continue"
    elif int(get_value(state, "retry_count", 0)) >= 2:
        # recovery 不能无限循环。预算耗尽后推进到下一步，让 synthesizer 解释缺失/失败信息。
        update["current_step"] = current + 1
        update["retry_count"] = 0
        update["next_action"] = "continue"
        update["trace"] = append_trace(state, f"execute: {selected_tool} recovery budget exhausted")
    else:
        update["next_action"] = "recover"
    return update


def recover_failed_step(state: AgentState | AgentStateDict) -> dict[str, Any]:
    """Recovery node：先改写 query 重试，再切换 fallback 工具。"""
    retry_count = int(get_value(state, "retry_count", 0))
    selected_tool = get_value(state, "selected_tool")
    tool_input = str(get_value(state, "tool_input", ""))
    if retry_count == 0:
        # 第一次失败通常可能是 query 太短或不够明确，所以先做 query rewrite。
        rewritten = f"{tool_input} latest reliable source"
        return {
            "tool_input": rewritten,
            "retry_count": 1,
            "next_action": "retry",
            "trace": append_trace(state, f"recover: rewritten query for {selected_tool}"),
        }

    # 第二次失败后仅切到语义上可信的 fallback；不相关的工具不会被错误调用。
    fallback = _fallback_for(str(selected_tool))
    if fallback is None:
        current = int(get_value(state, "current_step", 0))
        return {
            "current_step": current + 1,
            "retry_count": 0,
            "next_action": "skip",
            "trace": append_trace(state, f"recover: no safe fallback for {selected_tool}; skipped step"),
        }
    return {
        "selected_tool": fallback,
        "retry_count": retry_count + 1,
        "next_action": "retry",
        "trace": append_trace(state, f"recover: fallback {selected_tool} -> {fallback}"),
    }


def synthesize_answer(state: AgentStateDict, llm_client: LLMClient) -> dict[str, Any]:
    """Synthesis node：把原问题、计划和 working_memory 交给 LLM 生成最终答案。"""
    question = get_value(state, "question", "")
    plan = get_plan(state)
    answer = llm_client.synthesize(question, plan, get_value(state, "working_memory", []))
    return {
        "final_answer": answer,
        "trace": append_trace(state, "synthesizer: produced final answer"),
    }


def decide_after_route(state: AgentStateDict) -> str:
    """LangGraph 条件边：router 后决定是执行工具还是直接综合。"""
    return "synthesizer" if get_value(state, "next_action") == "synthesize" else "execute_tool"


def decide_after_execute(state: AgentStateDict) -> str:
    """LangGraph 条件边：工具执行后决定 recovery、继续路由，还是结束。"""
    if get_value(state, "next_action") == "recover":
        return "recover"
    plan = get_plan(state)
    current = int(get_value(state, "current_step", 0))
    if current >= len(plan):
        return "synthesizer"
    return "router"


def decide_after_recover(state: AgentStateDict) -> str:
    """Recovery may retry a tool or explicitly skip a step with no safe fallback."""
    return "router" if get_value(state, "next_action") == "skip" else "execute_tool"


def _fallback_for(tool_name: str) -> str | None:
    """Only use fallbacks that can plausibly answer the original subtask."""
    if tool_name == "web_search":
        return "knowledge_base"
    if tool_name == "knowledge_base":
        return "web_search"
    return None
