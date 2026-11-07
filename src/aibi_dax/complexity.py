"""Complexity metrics for DAX expressions.

Weights and thresholds are heuristics tuned so that a typical measure keeps a
low score while iterator-heavy switch-stairs stand out clearly (see tests).
"""

from __future__ import annotations

import re

from .lexer import tokenize
from .model_io import Measure, Model

ITERATORS = (
    "SUMX", "AVERAGEX", "MAXX", "MINX", "COUNTX", "COUNTAX", "CONCATENATEX", "RANKX", "PRODUCTX",
)


def count_functions(expr: str) -> int:
    """Number of function-call sites, identified by WORD( adjacency."""
    if "(" not in expr:
        return 0
    toks = tokenize(expr)
    return sum(
        1 for i, t in enumerate(toks)
        if t.kind == "word"
        and i + 1 < len(toks)
        and toks[i + 1].value == "("
    )


def paren_depth(expr: str) -> int:
    """Maximal nesting depth of parentheses, matching brackets ignored."""
    depth = 0
    worst = 0
    for ch in expr:
        if ch == "(":
            depth += 1
            worst = max(worst, depth)
        elif ch == ")":
            depth = max(0, depth - 1)
    return worst


def report(expr: str) -> dict[str, int]:
    """All elementary metrics for one expression."""
    return {
        "tokens": len(tokenize(expr)),
        "lines": 1 + expr.count("\n"),
        "chars": len(expr),
        "functions": count_functions(expr),
        "depth": paren_depth(expr),
        "iterators": sum(
            1 for m in re.finditer(r"\b[A-Z]+X\s*\(", expr)
            if m.group(0).split()[0].rstrip("(").strip() in ITERATORS
        ),
    }


def weight(expr: str) -> int:
    """Single weighted complexity score for one expression."""
    m = report(expr)
    return (
        m["tokens"]
        + 3 * m["functions"]
        + 5 * m["depth"]
        + 20 * m["iterators"]
    )


def rank_measures(model: Model, top: int = 10) -> list[tuple[str, str, int]]:
    """The `top` most complex measures as (table, name, weight), heaviest first."""
    scored: list[tuple[str, str, int]] = []
    for table in model.get("tables", []):
        for measure in table.get("measures", []):
            expr = str(measure.get("expression", ""))
            scored.append((str(table.get("name", "?")), str(measure.get("name", "?")), weight(expr)))
    scored.sort(key=lambda item: (item[2], item[1]), reverse=True)
    return scored[: max(0, top)]


_ = Measure  # re-export for type consumers
