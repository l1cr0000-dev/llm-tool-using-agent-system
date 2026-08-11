from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(slots=True)
class ToolResult:
    """所有工具统一返回这个结构。

    这样 execute_tool 和 recover 不需要关心工具内部细节：
    ok=True 就推进下一步；ok=False 就进入 recovery。
    """

    ok: bool
    tool: str
    data: dict[str, Any] | None = None
    error: str | None = None

    def to_memory(self) -> dict[str, Any]:
        """转成 working_memory 需要的基础字段。"""
        return {
            "tool": self.tool,
            "ok": self.ok,
            "data": self.data,
            "error": self.error,
        }


class AgentTool(Protocol):
    """工具协议：任何实现 name + run(query) 的类都能注册进 ToolRegistry。"""

    name: str

    def run(self, query: str) -> ToolResult:
        """Execute the tool for a natural-language query."""
