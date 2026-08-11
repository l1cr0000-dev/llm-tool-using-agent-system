from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, TypedDict


@dataclass(slots=True)
class PlanStep:
    """LLM 规划出来的一个任务步骤。

    id 用于保持执行顺序；objective 是这一小步要完成什么；
    tool 是 router 后续要调用的工具名。
    """

    id: int
    objective: str
    tool: str

    @classmethod
    def from_obj(cls, value: "PlanStep | dict[str, Any]") -> "PlanStep":
        # LangGraph state 里通常是 dict；测试里有时直接用 PlanStep。
        # 这个转换函数让两种形式都能被节点统一处理。
        if isinstance(value, PlanStep):
            return value
        return cls(id=int(value["id"]), objective=str(value["objective"]), tool=str(value["tool"]))

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "objective": self.objective, "tool": self.tool}


@dataclass(slots=True)
class AgentState:
    """面向人阅读的 state 版本，主要用于测试和说明字段含义。"""

    question: str
    plan: list[PlanStep] = field(default_factory=list)
    current_step: int = 0
    selected_tool: str | None = None
    tool_input: str | None = None
    tool_results: list[dict[str, Any]] = field(default_factory=list)
    working_memory: list[dict[str, Any]] = field(default_factory=list)
    retry_count: int = 0
    next_action: str | None = None
    final_answer: str | None = None
    trace: list[str] = field(default_factory=list)


class AgentStateDict(TypedDict, total=False):
    """LangGraph 实际运行时使用的 state 类型。

    TypedDict 比普通 dict 更适合表达 graph state 的字段契约；
    但 total=False 允许 node 只返回本次要更新的部分字段。
    """

    question: str
    plan: list[dict[str, Any] | PlanStep]
    current_step: int
    selected_tool: str | None
    tool_input: str | None
    tool_results: list[dict[str, Any]]
    working_memory: list[dict[str, Any]]
    retry_count: int
    next_action: str | None
    final_answer: str | None
    trace: list[str]


def get_value(state: AgentState | AgentStateDict, key: str, default: Any = None) -> Any:
    """同时兼容 dataclass state 和 LangGraph dict state 的取值函数。"""
    if isinstance(state, AgentState):
        return getattr(state, key, default)
    return state.get(key, default)


def get_plan(state: AgentState | AgentStateDict) -> list[PlanStep]:
    """把 state 中的 plan 统一转成 PlanStep，便于节点使用。"""
    return [PlanStep.from_obj(step) for step in get_value(state, "plan", [])]


def append_trace(state: AgentState | AgentStateDict, message: str) -> list[str]:
    """trace 是给 CLI 和面试演示看的执行轨迹。"""
    return [*get_value(state, "trace", []), message]
