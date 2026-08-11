from __future__ import annotations

import json
import os
import re
from typing import Any, Protocol

from openai import OpenAI

from tool_agent.state import PlanStep


AVAILABLE_TOOLS = ("web_search", "calculator", "knowledge_base", "get_time", "get_weather", "synthesize")
PLAN_FUNCTION = {
    "type": "function",
    "function": {
        "name": "create_execution_plan",
        "description": "Create the ordered, minimal execution plan for an agent task.",
        "parameters": {
            "type": "object",
            "properties": {
                "steps": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "objective": {"type": "string"},
                            "tool": {"type": "string", "enum": list(AVAILABLE_TOOLS)},
                        },
                        "required": ["objective", "tool"],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["steps"],
            "additionalProperties": False,
        },
    },
}


class LLMClient(Protocol):
    """LLM 抽象接口。

    图节点只依赖这个协议，不依赖 DeepSeek 具体实现。
    这样测试时可以注入 FakeLLMClient，离线时可以用 HeuristicLLMClient。
    """

    def plan(self, question: str) -> list[PlanStep]:
        """Return ordered steps with a tool name per step."""

    def synthesize(
        self,
        question: str,
        plan: list[PlanStep],
        working_memory: list[dict[str, Any]],
    ) -> str:
        """Return the final answer."""


class FakeLLMClient:
    """测试专用 LLM：返回固定 plan 和 answer，避免单元测试依赖外部 API。"""

    def __init__(self, plan: list[dict[str, Any]], answer: str) -> None:
        self._plan = [PlanStep.from_obj(item) for item in plan]
        self._answer = answer

    def plan(self, question: str) -> list[PlanStep]:
        return self._plan

    def synthesize(
        self,
        question: str,
        plan: list[PlanStep],
        working_memory: list[dict[str, Any]],
    ) -> str:
        return self._answer


class HeuristicLLMClient:
    """Offline fallback that preserves the pipeline shape when no API key exists."""

    def plan(self, question: str) -> list[PlanStep]:
        # 这个 fallback 不追求智能，只保证没有 API key 时也能演示完整 pipeline。
        lowered = question.lower()
        steps: list[PlanStep] = []
        if any(word in lowered or word in question for word in ["time", "时间", "几点", "当前"]):
            steps.append(PlanStep(id=len(steps) + 1, objective=self._location_objective(question, "获取当前时间"), tool="get_time"))
        if any(word in lowered or word in question for word in ["weather", "天气", "气温", "下雨"]):
            steps.append(PlanStep(id=len(steps) + 1, objective=self._location_objective(question, "获取当前天气"), tool="get_weather"))
        if any(word in lowered for word in ["calculate", "compute"]) or re.search(r"\d+\s*[-+*/]\s*\d+", question):
            steps.append(PlanStep(id=len(steps) + 1, objective=question, tool="calculator"))
        if any(word in lowered or word in question for word in ["知识库", "rag", "dify", "langgraph", "agent"]):
            steps.append(PlanStep(id=len(steps) + 1, objective=question, tool="knowledge_base"))
        if any(word in lowered for word in ["search", "latest", "news"]) or "最新" in question:
            steps.append(PlanStep(id=len(steps) + 1, objective=question, tool="web_search"))
        if not steps:
            steps.append(PlanStep(id=1, objective=question, tool="knowledge_base"))
        steps.append(PlanStep(id=len(steps) + 1, objective="综合已有信息回答用户问题", tool="synthesize"))
        return steps

    def synthesize(
        self,
        question: str,
        plan: list[PlanStep],
        working_memory: list[dict[str, Any]],
    ) -> str:
        facts = []
        for item in working_memory:
            if item.get("ok"):
                facts.append(f"- {item['objective']}: {item.get('data')}")
            else:
                facts.append(f"- {item['objective']}: failed ({item.get('error')})")
        joined = "\n".join(facts) if facts else "- 没有可用工具结果。"
        return f"基于工具执行结果回答：\n{joined}\n\n问题：{question}"

    def _location_objective(self, question: str, prefix: str) -> str:
        return f"{prefix}: {question}"


class DeepSeekLLMClient:
    """真实 DeepSeek 客户端。

    DeepSeek 使用 OpenAI-compatible API，所以这里直接复用 openai SDK。
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str = "https://api.deepseek.com",
    ) -> None:
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY")
        self.model = model or os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
        if not self.api_key:
            raise ValueError("DEEPSEEK_API_KEY is not configured")
        self.client = OpenAI(api_key=self.api_key, base_url=base_url)

    def plan(self, question: str) -> list[PlanStep]:
        # 优先通过 Function Calling 返回受约束的计划；失败时兼容旧模型的 JSON 文本输出。
        prompt = (
            "你是任务规划器。把用户问题拆成最少必要步骤。"
            "每步必须选择一个工具：web_search, calculator, knowledge_base, get_time, get_weather, synthesize。"
            "最后一步必须是 synthesize；不要执行工具，只创建计划。"
        )
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "system", "content": prompt}, {"role": "user", "content": question}],
                tools=[PLAN_FUNCTION],
                tool_choice={"type": "function", "function": {"name": "create_execution_plan"}},
                temperature=0.2,
            )
            calls = response.choices[0].message.tool_calls or []
            if calls:
                return self._normalise_plan(json.loads(calls[0].function.arguments).get("steps", []))
        except Exception:
            # 部分兼容模型可能不支持强制 tool_choice；回退到 JSON prompt，保持可用性。
            pass

        content = self._chat(prompt + "只返回 JSON 数组，每项包含 id, objective, tool。", question)
        return self._normalise_plan(json.loads(self._extract_json(content)))

    def synthesize(
        self,
        question: str,
        plan: list[PlanStep],
        working_memory: list[dict[str, Any]],
    ) -> str:
        # synthesizer 只看 working_memory，避免模型编造未由工具验证的信息。
        prompt = "你是答案综合器。只基于 working_memory 的工具结果回答，缺失信息要说明。"
        user = json.dumps(
            {
                "question": question,
                "plan": [step.to_dict() for step in plan],
                "working_memory": working_memory,
            },
            ensure_ascii=False,
        )
        return self._chat(prompt, user)

    def _chat(self, system: str, user: str) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0.2,
        )
        return response.choices[0].message.content or ""

    def _extract_json(self, content: str) -> str:
        # 兼容模型偶尔把 JSON 包在解释文本或代码块附近的情况。
        match = re.search(r"\[[\s\S]*\]", content)
        return match.group(0) if match else content

    def _normalise_plan(self, raw_steps: Any) -> list[PlanStep]:
        """Validate model output before it becomes executable agent state."""
        if not isinstance(raw_steps, list):
            raise ValueError("planner output must contain a steps array")
        steps: list[PlanStep] = []
        for item in raw_steps:
            if not isinstance(item, dict):
                raise ValueError("planner step must be an object")
            tool = str(item.get("tool", ""))
            objective = str(item.get("objective", "")).strip()
            if tool not in AVAILABLE_TOOLS or not objective:
                raise ValueError("planner returned an invalid tool or empty objective")
            if tool != "synthesize":
                steps.append(PlanStep(id=len(steps) + 1, objective=objective, tool=tool))
        steps.append(PlanStep(id=len(steps) + 1, objective="综合已有信息回答用户问题", tool="synthesize"))
        return steps


def create_default_llm() -> LLMClient:
    """根据环境变量选择真实 DeepSeek 或本地 fallback。"""
    if os.getenv("DEEPSEEK_API_KEY"):
        return DeepSeekLLMClient()
    return HeuristicLLMClient()
