"""Deterministic arithmetic via a restricted AST evaluator (no eval)."""
from __future__ import annotations

import ast
import math
import operator

from pydantic import BaseModel, Field

from app.tools.registry import BaseTool, ToolError, register

_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
        ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod, ast.Pow: operator.pow,
        ast.USub: operator.neg, ast.UAdd: operator.pos}
_FUNCS = {"round": round, "abs": abs, "min": min, "max": max, "sqrt": math.sqrt, "ceil": math.ceil,
          "floor": math.floor}


def safe_eval(expr: str) -> float:
    if len(expr) > 300:
        raise ToolError("expression too long")
    try:
        tree = ast.parse(expr.replace("^", "**"), mode="eval")
    except SyntaxError as e:
        raise ToolError(f"invalid expression: {e.msg}") from e

    def ev(n: ast.AST) -> float:
        if isinstance(n, ast.Expression):
            return ev(n.body)
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)) and not isinstance(n.value, bool):
            return n.value
        if isinstance(n, ast.BinOp) and type(n.op) in _OPS:
            a, b = ev(n.left), ev(n.right)
            if isinstance(n.op, ast.Pow) and abs(b) > 100:
                raise ToolError("exponent too large")
            try:
                return _OPS[type(n.op)](a, b)
            except ZeroDivisionError as e:
                raise ToolError("division by zero") from e
        if isinstance(n, ast.UnaryOp) and type(n.op) in _OPS:
            return _OPS[type(n.op)](ev(n.operand))
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in _FUNCS and not n.keywords:
            return _FUNCS[n.func.id](*[ev(a) for a in n.args])
        raise ToolError(f"unsupported element in expression: {type(n).__name__}")

    return ev(tree)


class CalcIn(BaseModel):
    expression: str = Field(description="Arithmetic expression, e.g. '(12 * 4.5) + 3' or 'round(250/7, 2)'")


class CalcOut(BaseModel):
    expression: str
    result: float


@register
class CalculatorTool(BaseTool):
    name = "calculator"
    description = "Evaluates arithmetic expressions deterministically (+ - * / // % ** round abs min max sqrt)."
    selection_hint = ("Needed when users will ask for totals, differences, prorations, unit conversions, "
                      "price x quantity or any other numeric computation over facts from the documents.")
    input_model = CalcIn
    output_model = CalcOut

    def execute(self, inp: CalcIn, ctx):
        return {"expression": inp.expression, "result": float(safe_eval(inp.expression))}, []
