# Agent Architecture Notes

LangGraph is useful for stateful agent workflows because each node receives and returns explicit graph state. This project uses that pattern for planning, routing, tool execution, failure recovery, working memory, and final synthesis.

Dify is useful for low-code workflow comparison. It can represent a similar flow with visual workflow nodes, but code-based LangGraph gives finer control over retry policy, fallback tools, test doubles, and internal state inspection.

RAG lets the agent answer from a curated local knowledge base before falling back to web search. In this demo, the knowledge base is intentionally small so the retrieval behavior is easy to inspect.
