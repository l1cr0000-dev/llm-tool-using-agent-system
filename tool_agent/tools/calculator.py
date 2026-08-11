from __future__ import annotations

import ast
import operator
import re
from typing import Callable

from tool_agent.tools.base import ToolResult


class CalculatorTool:
    """安全计算器。

    只允许 AST 里的数字、二元运算和一元正负号；不会执行函数调用、属性访问、
    import 等危险代码。
    """

    name = "calculator"

    # AST node type -> 实际 Python 运算函数。白名单越小，安全边界越清楚。
    _operators: dict[type[ast.AST], Callable[[float, float], float]] = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.FloorDiv: operator.floordiv,
        ast.Mod: operator.mod,
        ast.Pow: operator.pow,
    }
    _unary: dict[type[ast.AST], Callable[[float], float]] = {
        ast.UAdd: operator.pos,
        ast.USub: operator.neg,
    }

    def run(self, query: str) -> ToolResult:
        try:
            # 用户常输入“请计算 1+2”，这里先抽取自然语言中的算术片段。
            expr = self._extract_expression(query)
            parsed = ast.parse(expr, mode="eval")
            value = self._eval(parsed.body)
        except Exception as exc:
            return ToolResult(ok=False, tool=self.name, error=str(exc))
        return ToolResult(ok=True, tool=self.name, data={"expression": expr, "value": value})

    def _extract_expression(self, query: str) -> str:
        cleaned = query.strip()
        if not cleaned:
            raise ValueError("empty expression is not allowed")
        # 找出包含数字和运算符的最长片段，例如“计算 128 * 37 / 16，并说明过程”。
        candidates = [
            candidate.strip()
            for candidate in re.findall(r"[\d\s\.\+\-\*/%\(\)]+", cleaned)
            if re.search(r"\d", candidate) and re.search(r"[-+\*/%]", candidate)
        ]
        if not candidates:
            return cleaned
        return max(candidates, key=len)

    def _eval(self, node: ast.AST) -> float:
        # 递归解释 AST。遇到白名单之外的节点就拒绝。
        if isinstance(node, ast.Constant) and isinstance(node.value, int | float):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in self._operators:
            return self._operators[type(node.op)](self._eval(node.left), self._eval(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in self._unary:
            return self._unary[type(node.op)](self._eval(node.operand))
        raise ValueError(f"expression node {type(node).__name__} is not allowed")
