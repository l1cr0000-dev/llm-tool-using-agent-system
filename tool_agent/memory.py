from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from tool_agent.tools.base import ToolResult


@dataclass(slots=True)
class WorkingMemory:
    """跨步骤工作记忆。

    这里故意不用“把所有历史消息拼回 prompt”的方式，而是记录结构化事实：
    哪一步、调用了什么工具、成功与否、返回了什么数据。
    """

    entries: list[dict[str, Any]] = field(default_factory=list)

    def record_step(self, step_id: int, objective: str, tool_result: ToolResult) -> None:
        # 统一 memory schema，方便 synthesizer 和测试读取。
        self.entries.append(
            {
                "step_id": step_id,
                "objective": objective,
                "tool": tool_result.tool,
                "ok": tool_result.ok,
                "data": tool_result.data,
                "error": tool_result.error,
            }
        )


def append_memory(
    entries: list[dict[str, Any]],
    step_id: int,
    objective: str,
    tool_result: ToolResult,
) -> list[dict[str, Any]]:
    """不可变风格地追加 memory。

    LangGraph node 推荐返回“更新后的字段”，所以这里复制旧 entries 后追加新记录。
    """
    memory = WorkingMemory(entries=[*entries])
    memory.record_step(step_id=step_id, objective=objective, tool_result=tool_result)
    return memory.entries
