from __future__ import annotations

import os
from pathlib import Path

from tool_agent.tools.base import AgentTool, ToolResult
from tool_agent.tools.calculator import CalculatorTool
from tool_agent.tools.knowledge_base import KnowledgeBaseTool
from tool_agent.tools.time_tool import TimeTool
from tool_agent.tools.travel import DestinationGuideTool, TransportQuoteTool
from tool_agent.tools.weather import WeatherTool
from tool_agent.tools.web_search import TavilyClient, WebSearchTool


class ToolRegistry:
    def __init__(self, tools: list[AgentTool] | None = None, allow_external_tools: bool = True) -> None:
        # tools 参数用于测试注入 fake tools；真实运行时使用默认工具集。
        if tools is None:
            tavily_key = os.getenv("TAVILY_API_KEY") if allow_external_tools else None
            web_client = TavilyClient(tavily_key) if tavily_key else None
            project_root = Path(__file__).resolve().parents[2]
            # 默认工具集对应简历项目里的 multi-tool architecture。
            tools = [
                WebSearchTool(web_client),
                CalculatorTool(),
                KnowledgeBaseTool(project_root / "sample_kb"),
                TransportQuoteTool(),
                DestinationGuideTool(project_root / "travel_kb" / "destinations.json"),
                TimeTool(),
                WeatherTool(),
            ]
        self._tools = {tool.name: tool for tool in tools}

    @property
    def names(self) -> list[str]:
        return sorted(self._tools)

    def run(self, name: str, query: str) -> ToolResult:
        # 未知工具不抛异常，而是返回结构化失败，交给 recovery 处理。
        tool = self._tools.get(name)
        if tool is None:
            return ToolResult(ok=False, tool=name, error=f"unknown tool: {name}")
        return tool.run(query)
