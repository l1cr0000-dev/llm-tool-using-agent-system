from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests

from tool_agent.tools.base import ToolResult


@dataclass(slots=True)
class TavilyClient:
    """Tavily API 客户端。

    这里不把 Tavily 逻辑写进 WebSearchTool，是为了让工具层更容易替换供应商。
    """

    api_key: str
    timeout: float = 15.0

    def search(self, query: str, max_results: int = 5) -> dict[str, Any]:
        response = requests.post(
            "https://api.tavily.com/search",
            json={"api_key": self.api_key, "query": query, "max_results": max_results},
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError("Tavily returned non-object JSON")
        return data


class WebSearchTool:
    """联网搜索工具。

    如果没有 TAVILY_API_KEY，不直接崩溃，而是返回 ToolResult(ok=False)；
    这样 graph 可以演示 failure recovery 和 fallback tool。
    """

    name = "web_search"

    def __init__(self, client: TavilyClient | None = None) -> None:
        self.client = client

    def run(self, query: str) -> ToolResult:
        if self.client is None:
            return ToolResult(ok=False, tool=self.name, error="TAVILY_API_KEY is not configured")
        try:
            data = self.client.search(query)
        except Exception as exc:
            return ToolResult(ok=False, tool=self.name, error=str(exc))
        results = data.get("results", [])
        if not results:
            return ToolResult(ok=False, tool=self.name, error="web search returned no results")
        # 保留 Tavily 原始 result 字段，synthesizer 可以看到 title/url/content/score。
        return ToolResult(ok=True, tool=self.name, data={"query": query, "results": results})
