"""Anti-pattern rules for DAX expressions.

Each rule takes an expression string and returns a human-readable finding,
or None when the expression follows the rule. Rules are pure: no IO, no
regex compile side effects beyond module level.
"""

from __future__ import annotations

import re
from collections.abc import Callable

from .parser import Binary, Call, Node, ParseError, Unary, parse

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


def iferror_overuse(expr: str) -> str | None:
    """IFERROR masks model bugs behind silent blanks — an explicit error
    contract (or DIVIDE's third argument) says what you mean."""
    if re.search(r"\bIFERROR\s*\(", expr, re.IGNORECASE):
        return "IFERROR wraps the whole expression — verify you want silent blank on failure; prefer DIVIDE's third argument or explicit guards."
    return None


_SELECTEDVALUE_RE = re.compile(r"HASONEVALUE\s*\(", re.IGNORECASE)


def values_with_hasonevalue(expr: str) -> str | None:
    """HASONEVALUE + VALUES is the long-form SELECTEDVALUE."""
    if _SELECTEDVALUE_RE.search(expr) and re.search(r"\bVALUES\s*\(", expr, re.IGNORECASE):
        return "HASONEVALUE + VALUES — replace the pair with SELECTEDVALUE for the same semantics in one call."
    return None


_LOWER_CALL_RE = re.compile(r"\b[a-z][a-z0-9_]*\s*\(")


def lowercase_function(expr: str) -> str | None:
    """DAX has no lowercase callable identifiers, so a bare lowercase word
    before ( is almost always a mistyped function name.

    String literals and bracketed columns are stripped first — they are the
    two places real text like 'computed(x)' legitimately appears."""
    stripped = re.sub(r'"[^"]*"|\'[^\']*\'', "", expr)
    stripped = re.sub(r"\[[^\]]*\]", "", stripped)
    match = _LOWER_CALL_RE.search(stripped)
    if match:
        return f"Lowercase function call {match.group(0).strip()} — DAX function names are written UPPERCASE."
    return None


def _iterator_depth(node: Node) -> int:
    """How many row-iterator Calls sit on the deepest path of the tree."""
    match node:
        case Call(name=name, args=args):
            child = max((_iterator_depth(a) for a in args), default=0)
            return child + 1 if name.upper() in ITERATORS else child
        case Binary(left=left, right=right):
            return max(_iterator_depth(left), _iterator_depth(right))
        case Unary(operand=operand):
            return _iterator_depth(operand)
        case _:
            return 0


def nested_iterators(expr: str) -> str | None:
    """An iterator inside another iterator pays a context transition per
    row — usually a VAR capture of the outer step computes the same result
    for a fraction of the effort.

    Expressions the parser cannot reduce fall back to None: the token-based
    rules above still cover the text level.
    """
    try:
        tree = parse(expr)
    except ParseError:
        return None
    depth = _iterator_depth(tree)
    if depth >= 2:
        return (
            f"{depth} iterators deep — every iterator row pays a context "
            "transition; capture the outer step in a VAR and aggregate over it."
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
    iferror_overuse,
    values_with_hasonevalue,
    lowercase_function,
    nested_iterators,
]
