from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from tool_agent.tools.base import ToolResult


@dataclass(slots=True)
class KnowledgeChunk:
    """一个被检索到的本地知识片段。"""

    source: str
    text: str
    score: int


class KnowledgeBaseTool:
    """极简 RAG 工具。

    为了让项目容易讲清楚，这里不用向量数据库，而是用 markdown 分块 + 关键词计分。
    真实项目中可以把 _load_chunks/_terms/ranking 换成 embedding + vector store。
    """

    name = "knowledge_base"

    def __init__(self, kb_dir: str | Path = "sample_kb", max_matches: int = 3) -> None:
        self.kb_dir = Path(kb_dir)
        self.max_matches = max_matches

    def run(self, query: str) -> ToolResult:
        chunks = self._load_chunks()
        if not chunks:
            return ToolResult(ok=False, tool=self.name, error=f"no knowledge files found in {self.kb_dir}")

        terms = self._terms(query)
        ranked = []
        for source, text in chunks:
            # 朴素打分：query term 在 chunk 中出现越多，相关性越高。
            score = sum(text.lower().count(term) for term in terms)
            if score:
                ranked.append(KnowledgeChunk(source=source, text=text, score=score))

        ranked.sort(key=lambda item: item.score, reverse=True)
        if not ranked:
            return ToolResult(ok=False, tool=self.name, error="no matching knowledge base chunks")

        return ToolResult(
            ok=True,
            tool=self.name,
            data={
                "query": query,
                "matches": [
                    {"source": item.source, "text": item.text, "score": item.score}
                    for item in ranked[: self.max_matches]
                ],
            },
        )

    def _load_chunks(self) -> list[tuple[str, str]]:
        if not self.kb_dir.exists():
            return []
        chunks: list[tuple[str, str]] = []
        for path in sorted(self.kb_dir.glob("**/*")):
            if path.suffix.lower() not in {".md", ".txt"} or not path.is_file():
                continue
            text = path.read_text(encoding="utf-8")
            # 空行分块，保持实现简单，也方便观察检索命中的原文。
            for block in re.split(r"\n\s*\n", text):
                clean = block.strip()
                if clean:
                    chunks.append((path.name, clean))
        return chunks

    def _terms(self, query: str) -> list[str]:
        # 支持英文单词和中文连续片段；长度为 1 的词通常噪声较大。
        return [term.lower() for term in re.findall(r"[\w\u4e00-\u9fff]+", query) if len(term) > 1]
