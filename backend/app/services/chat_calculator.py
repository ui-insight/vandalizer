"""Exact arithmetic for chat: the ``calculate`` tool.

Support ticket (NIH R01 budget): asked whether a 5-year budget adds up, chat
summed the yearly direct costs in its head. It left out the "Other" row, got
four of five years wrong, said none of five indirect amounts fell in a range
that four of them were in, and called a total "arithmetically impossible"
that sat inside its own bounds. Language models are unreliable at multi-term
addition and worse at comparing many numbers at once.

So arithmetic is a tool. The model writes each step as a labelled expression
over numbers it read from the document; this module evaluates it exactly
(``Decimal``, no floats drifting a cent) and returns every step, so the reply
can show the working and the figures it states are ones the tool computed.

Expressions are parsed with :mod:`ast` and only arithmetic is allowed:
numbers, ``+ - * / // % **``, parentheses, comparisons (``<= <`` chains, ``==``),
``and``/``or``/``not``, and ``sum min max abs round``. An earlier step's result
is referenced as ``{label}``. Nothing else — no names, attributes, calls to
anything else — so an expression copied from a document can't run code.
"""

from __future__ import annotations

import ast
import re
from decimal import ROUND_HALF_UP, Decimal, localcontext
from typing import Any

from pydantic import BaseModel, Field
from pydantic_ai.tools import RunContext

from app.services.chat_deps import AgenticChatDeps

MAX_STEPS = 60
MAX_EXPRESSION = 2000
MAX_POWER = 12
_REF = re.compile(r"\{([^{}]{1,120})\}")
# "1,250,000" inside an expression is ambiguous with sum(1, 250, 000); refuse it
# with a clear message rather than guess.
_GROUPED = re.compile(r"\d,\d{3}(?!\d)")
_CURRENCY = re.compile(r"[$€£]")


class Calculation(BaseModel):
    label: str = Field(description="What this step computes, e.g. 'Y1 direct costs'. Later steps can use it as {Y1 direct costs}.")
    expression: str = Field(description="Arithmetic over numbers read from the source, e.g. '200000 + 15000 + 8000 + 20000 + 10000'. No thousands separators.")


class CalculationError(ValueError):
    pass


def _number(value: Decimal | bool) -> Decimal:
    if isinstance(value, bool):
        raise CalculationError("A true/false result can't be used as a number.")
    return value


def _evaluate(node: ast.AST) -> Decimal | bool:
    if isinstance(node, ast.Expression):
        return _evaluate(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return Decimal(str(node.value))
    if isinstance(node, ast.UnaryOp):
        operand = _evaluate(node.operand)
        if isinstance(node.op, ast.Not):
            return not operand
        if isinstance(node.op, ast.USub):
            return -_number(operand)
        if isinstance(node.op, ast.UAdd):
            return _number(operand)
    if isinstance(node, ast.BinOp):
        left, right = _number(_evaluate(node.left)), _number(_evaluate(node.right))
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, (ast.Div, ast.FloorDiv, ast.Mod)) and right == 0:
            raise CalculationError("Division by zero.")
        if isinstance(node.op, ast.Div):
            return left / right
        if isinstance(node.op, ast.FloorDiv):
            return left // right
        if isinstance(node.op, ast.Mod):
            return left % right
        if isinstance(node.op, ast.Pow):
            if abs(right) > MAX_POWER or right != right.to_integral_value():
                raise CalculationError(f"Powers must be whole numbers up to {MAX_POWER}.")
            return left ** int(right)
    if isinstance(node, ast.BoolOp):
        values = [_evaluate(v) for v in node.values]
        return all(values) if isinstance(node.op, ast.And) else any(values)
    if isinstance(node, ast.Compare):
        left = _number(_evaluate(node.left))
        for op, comparator in zip(node.ops, node.comparators):
            right = _number(_evaluate(comparator))
            ok = {ast.Lt: left < right, ast.LtE: left <= right, ast.Gt: left > right,
                  ast.GtE: left >= right, ast.Eq: left == right, ast.NotEq: left != right}.get(type(op))
            if ok is None:
                raise CalculationError("Use <, <=, >, >=, == or != to compare.")
            if not ok:
                return False
            left = right
        return True
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and not node.keywords:
        args = [_number(_evaluate(a)) for a in node.args]
        name = node.func.id
        if name == "sum":
            return sum(args, Decimal(0))
        if name in {"min", "max"} and args:
            return min(args) if name == "min" else max(args)
        if name == "abs" and len(args) == 1:
            return abs(args[0])
        if name == "round" and len(args) in (1, 2):
            places = int(args[1]) if len(args) == 2 else 0
            if not -9 <= places <= 9:
                raise CalculationError("round() places must be between -9 and 9.")
            return args[0].quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)
    if isinstance(node, (ast.List, ast.Tuple)):
        raise CalculationError("Pass the numbers to sum/min/max directly, e.g. sum(1, 2, 3).")
    raise CalculationError("Only numbers, + - * / // % **, comparisons, and/or/not, and sum/min/max/abs/round are allowed.")


def _display(value: Decimal) -> str:
    """Grouped, without trailing zeros: 1255000 → '1,255,000', 0.275 → '0.275'."""
    if value == value.to_integral_value():
        return f"{int(value):,}"
    text = f"{value.normalize():,f}"
    return text


def evaluate(expression: str, results: dict[str, Decimal | bool]) -> tuple[str, Decimal | bool]:
    """Evaluate one expression, with ``{label}`` replaced by earlier results."""
    if len(expression) > MAX_EXPRESSION:
        raise CalculationError(f"Keep each expression under {MAX_EXPRESSION} characters; split it into steps.")

    def substitute(match: re.Match[str]) -> str:
        key = match.group(1).strip()
        if key not in results:
            raise CalculationError(f"No earlier step is labelled “{key}”.")
        value = results[key]
        if isinstance(value, bool):
            raise CalculationError(f"“{key}” is a true/false check, not a number.")
        return f"({value})"

    resolved = _REF.sub(substitute, expression)
    text = _CURRENCY.sub("", resolved).replace("×", "*").replace("−", "-").strip()
    if _GROUPED.search(text):
        raise CalculationError(
            "Write numbers without thousands separators (1250000, not 1,250,000), "
            "and separate sum() arguments with a comma and a space."
        )
    try:
        tree = ast.parse(text, mode="eval")
    except SyntaxError as exc:
        raise CalculationError(f"Not a valid expression: {exc.msg}.") from exc
    with localcontext() as ctx:
        ctx.prec = 34
        try:
            value = _evaluate(tree)
            if isinstance(value, Decimal) and not value.is_finite():
                raise CalculationError("The result is undefined or too large to compute.")
        except (ArithmeticError, RecursionError) as exc:
            # InvalidOperation/Overflow/DivisionByZero are ArithmeticErrors;
            # a long run of unary signs recurses past the stack limit.
            raise CalculationError("The arithmetic could not be completed.") from exc
    return resolved, value


def _shown(value: Decimal) -> Decimal:
    """Rounded to six decimal places for display only; later steps that
    refer to this one get the full-precision value."""
    if value == value.to_integral_value():
        return value
    with localcontext() as ctx:
        ctx.prec = 60
        return value.quantize(Decimal("1e-6")).normalize()


def run(calculations: list[Calculation]) -> dict[str, Any]:
    if not calculations:
        return {"error": "Give at least one calculation."}
    if len(calculations) > MAX_STEPS:
        return {"error": f"At most {MAX_STEPS} steps per call; split the work."}
    results: dict[str, Decimal | bool] = {}
    steps: list[dict[str, Any]] = []
    for item in calculations:
        label = item.label.strip() or f"Step {len(steps) + 1}"
        try:
            resolved, value = evaluate(item.expression, results)
        except CalculationError as exc:
            steps.append({"label": label, "expression": item.expression, "error": str(exc)})
            continue
        results[label] = value
        if isinstance(value, bool):
            steps.append({"label": label, "expression": resolved, "check": value,
                          "result": "true" if value else "false"})
        else:
            steps.append({"label": label, "expression": resolved, "result": _display(_shown(value))})
    return {
        "steps": steps,
        "note": (
            "Exact results for the numbers you supplied. They are only as right as those inputs: "
            "every term must be a value read from the source, with no row or year left out. "
            "Show these steps in your reply (label, the terms, the result) and state only these "
            "results; say they were calculated from the document. A step with an error was not "
            "computed: fix it and call again rather than estimating."
        ),
    }


async def calculate(context: RunContext[AgenticChatDeps], calculations: list[Calculation]) -> dict[str, Any]:
    """Do arithmetic exactly. Use it for EVERY total, difference, rate, share or
    range check you state about a document's figures — budget totals, whether a
    table adds up, indirect = total − direct, percentages, year-over-year changes.
    Never add, subtract or compare figures in your head.

    Each step is a label and an expression over numbers read from the source
    (no thousands separators). Refer to an earlier step as {label}. Checks are
    expressions too: '51000 <= {Y5 indirect} <= 57000' returns true/false.

    Before summing a category, list every row of the table that belongs to it
    (e.g. Personnel, Equipment, Travel, Supplies, Other) and include each one as a
    term, for every year. Show the steps in your reply as the working, state only
    the results returned here, and say they were calculated from the document.
    """
    return run(calculations)
