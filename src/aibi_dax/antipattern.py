"""Anti-pattern rules for DAX expressions.

Each rule takes an expression string and returns a human-readable finding,
or None when the expression follows the rule. Rules are pure: no IO, no
regex compile side effects beyond module level.
"""

from __future__ import annotations

import re
from collections.abc import Callable

# Iterator functions whose row context makes CALCULATE placement dangerous.
ITERATORS = {"SUMX", "AVERAGEX", "MAXX", "MINX", "COUNTX", "COUNTAX", "CONCATENATEX"}

IDENT_IT_RE = re.compile(r"\b([A-Z]+X)\s*\(")

Rule = Callable[[str], str | None]


def calculate_inside_iterator(expr: str) -> str | None:
    """CALCULATE inside a row-iterator: filter context is overridden per-row
    by the iterator, so the result is usually wrong or misleading.

    Iterator delimiters that would end scanning depth prematurely are not
    tracked across string literals; bracketed columns cannot contain ( or ),
    and quoted strings rarely wrap calls — acceptable for a heuristic lint.
    """
    for match in IDENT_IT_RE.finditer(expr):
        if match.group(1).upper() not in ITERATORS:
            continue
        depth = 1  # We stand just inside the iterator's opening paren.
        cursor = match.end()
        while cursor < len(expr) and depth:
            ch = expr[cursor]
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            elif re.match(r"CALCULATE\s*\(", expr[cursor:], re.IGNORECASE):
                return (
                    "CALCULATE inside a row iterator — the iterator's row context "
                    "shadows filters; hoist CALCULATE outside the iterator."
                )
            cursor += 1
    return None


def too_many_ifs(expr: str) -> str | None:
    """Three or more IF( call sites: SWITCH(TRUE(), ...) is flatter."""
    calls = len(re.findall(r"\bIF\s*\(", expr, re.IGNORECASE))
    if calls >= 3:
        return f"{calls} nested IF calls — SWITCH(TRUE(), ...) reads better and evaluates faster."
    return None


def raw_division(expr: str) -> str | None:
    """/ without DIVIDE( raises #NUM! on zero denominators.

    Quoted strings and quoted table names are stripped first so paths like
    "a/b" in literals do not trigger the rule.
    """
    stripped = re.sub(r'"[^"]*"|\'[^\']*\'', "", expr)
    if "DIVIDE(" in stripped.upper():
        return None
    if "/" in stripped:
        return "Raw '/' division — use DIVIDE(num, den) to absorb zero-denominator errors."
    return None


def blank_comparison(expr: str) -> str | None:
    """`= BLANK()` misses semantics; ISBLANK expresses intent."""
    if re.search(r"=\s*BLANK\s*\(", expr, re.IGNORECASE):
        return "Compare with ISBLANK(x), not `x = BLANK()` — equality against BLANK is unreliable."
    return None


def bare_all_table(expr: str) -> str | None:
    """Single-argument ALL(table) used as a filter eraser — REMOVEFILTERS is unambiguous."""
    if re.search(r"ALL\s*\(\s*'?[A-Za-z_][\w ]*'?\s*\)", expr):
        return "Bare ALL(table) — REMOVEFILTERS(table) is clearer when you only want filters gone."
    return None


def concat_ampersand(expr: str) -> str | None:
    """String concatenation '&' inside CONCATENATEX is redundant."""
    if re.search(r"CONCATENATEX\s*\(", expr, re.IGNORECASE) and "&" in re.sub(
        r'"[^"]*"', "", expr
    ):
        return "CONCATENATEX plus '&' — pass all parts as CONCATENATEX arguments instead."
    return None


def earlier_var(expr: str) -> str | None:
    """EARLIER is superseded by VAR capture — flat and type-checkable."""
    if re.search(r"\bEARLIER\s*\(", expr, re.IGNORECASE):
        return "EARLIER(...) is deprecated — capture the outer row with VAR and reference that variable."
    return None


_FIRST_ARG_ALL_RE = re.compile(
    r"\b(?:CALCULATE|[A-Z]+X)\s*\(\s*(?:ALL\b|FILTER\s*\(\s*ALL\b)",
    re.IGNORECASE,
)


def all_first_argument(expr: str) -> str | None:
    """An iterator or CALCULATE aggregating directly over ALL /
    FILTER(ALL(...)) walks every row through the filter machinery; a
    boolean filter in CALCULATE prunes earlier and reads better."""
    if _FIRST_ARG_ALL_RE.search(expr):
        return (
            "Aggregate over ALL(...)/FILTER(ALL(...)) as the first argument — "
            "prefer a boolean filter (Table[Col] = value) inside CALCULATE."
        )
    return None


ALL_RULES: list[Rule] = [
    calculate_inside_iterator,
    too_many_ifs,
    raw_division,
    blank_comparison,
    bare_all_table,
    concat_ampersand,
    earlier_var,
    all_first_argument,
]
