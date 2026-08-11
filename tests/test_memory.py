from __future__ import annotations

from tool_agent.memory import WorkingMemory
from tool_agent.tools.base import ToolResult


def test_working_memory_records_structured_step_result() -> None:
    memory = WorkingMemory()

    memory.record_step(
        step_id=1,
        objective="获取当前天气",
        tool_result=ToolResult(ok=True, tool="get_weather", data={"condition": "Clear"}),
    )

    assert memory.entries == [
        {
            "step_id": 1,
            "objective": "获取当前天气",
            "tool": "get_weather",
            "ok": True,
            "data": {"condition": "Clear"},
            "error": None,
        }
    ]
