"""Anti-pattern rules for DAX expressions.

Each rule takes an expression string and returns a human-readable finding,
or None when the expression follows the rule. Rules are pure: no IO, no
regex compile side effects beyond module level.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator

from .parser import (
    Binary,
    Call,
    ColumnRef,
    Ident,
    List,
    Literal,
    Node,
    ParseError,
    QualifiedColumn,
    TableRef,
    Unary,
    Var,
    parse,
)

# Iterator functions whose row context makes CALCULATE placement dangerous.
ITERATORS = {"SUMX", "AVERAGEX", "MAXX", "MINX", "COUNTX", "COUNTAX", "CONCATENATEX"}

IDENT_IT_RE = re.compile(r"\b([A-Z]+X)\s*\(")

Rule = Callable[[str], str | None]


_CALC_IN_IT_MSG = (
    "CALCULATE inside a row iterator — the iterator's row context "
    "shadows filters; hoist CALCULATE outside the iterator."
)


def calculate_inside_iterator(expr: str) -> str | None:
    """CALCULATE inside a row-iterator: filter context is overridden per-row
    by the iterator, so the result is usually wrong or misleading.

    AST-driven: any iterator call whose argument tree contains a CALCULATE
    call. Unparseable text keeps the conservative token scan.
    """
    try:
        tree = parse(expr)
    except ParseError:
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
                    return _CALC_IN_IT_MSG
                cursor += 1
        return None
    for call in _walk_calls(tree):
        if call.name.upper() in ITERATORS and any(_has_call(a, "CALCULATE") for a in call.args):
            return _CALC_IN_IT_MSG
    return None


def too_many_ifs(expr: str) -> str | None:
    """Three or more IF( call sites: SWITCH(TRUE(), ...) is flatter.

    Counted on the AST (Call nodes named IF); the legacy token regex serves
    as fallback when the expression does not parse.
    """
    try:
        tree = parse(expr)
    except ParseError:
        calls = len(re.findall(r"\bIF\s*\(", expr, re.IGNORECASE))
        return _ifs_finding(calls)
    return _ifs_finding(_count_calls(tree, "IF"))


def _ifs_finding(calls: int) -> str | None:
    if calls >= 3:
        return f"{calls} nested IF calls — SWITCH(TRUE(), ...) reads better and evaluates faster."
    return None


def _count_calls(node: Node, name: str) -> int:
    """Number of Call nodes with the given (case-insensitive) name."""
    match node:
        case Call(name=node_name, args=args):
            hits = sum(_count_calls(a, name) for a in args)
            return hits + (node_name.upper() == name)
        case Binary(left=left, right=right):
            return _count_calls(left, name) + _count_calls(right, name)
        case Unary(operand=operand):
            return _count_calls(operand, name)
        case Var(value=value, body=body):
            return _count_calls(value, name) + _count_calls(body, name)
        case _:
            return 0


def _has_call(node: Node, name: str) -> bool:
    return _count_calls(node, name) > 0


def _is_numeric_literal(node: Node) -> bool:
    """A numeric `Literal` (numbers tokenize without quote marks)."""
    return isinstance(node, Literal) and not node.text.startswith(("'", '"'))


def _raw_div_hit(node: Node) -> bool:
    """Any `/` binary whose right operand is not a numeric literal."""
    match node:
        case Binary(op="/", left=left, right=right):
            return not _is_numeric_literal(right) or _raw_div_hit(left)
        case Binary(left=left, right=right):
            return _raw_div_hit(left) or _raw_div_hit(right)
        case Call(_, args):
            return any(_raw_div_hit(a) for a in args)
        case Unary(operand=operand):
            return _raw_div_hit(operand)
        case Var(value=value, body=body):
            return _raw_div_hit(value) or _raw_div_hit(body)
        case _:
            return False


def raw_division(expr: str) -> str | None:
    """/ without DIVIDE( raises #NUM! on zero denominators.

    AST-driven: a `Binary('/')` whose denominator is not a numeric literal
    is the runtime trap — constant denominators cannot change under filter
    context. Any `DIVIDE(...)` anywhere suppresses the rule. Regex fallback
    (string-stripped text scan) when the expression does not parse.
    """
    try:
        tree = parse(expr)
    except ParseError:
        stripped = re.sub(r'"[^"]*"|\'[^\']*\'', "", expr)
        if "DIVIDE(" in stripped.upper():
            return None
        return _DIV_MSG if "/" in stripped else None
    if _has_call(tree, "DIVIDE"):
        return None
    return _DIV_MSG if _raw_div_hit(tree) else None


def blank_comparison(expr: str) -> str | None:
    """`= BLANK()` misses semantics; ISBLANK expresses intent.

    AST-driven: any `=` comparison against a zero-argument BLANK() call on
    either side; regex fallback when the expression does not parse.
    """
    try:
        tree = parse(expr)
    except ParseError:
        if re.search(r"=\s*BLANK\s*\(", expr, re.IGNORECASE):
            return _BLANK_MSG
        return None
    return _BLANK_MSG if _eq_blank(tree) else None


def _eq_blank(node: Node) -> bool:
    """An `=` comparison with a zero-argument BLANK() call on either side."""
    match node:
        case Binary(op="=", left=left, right=right):
            for side in (left, right):
                match side:
                    case Call(name="BLANK" | "blank", args=()):
                        return True
            return _eq_blank(left) or _eq_blank(right)
        case Call(_, args):
            return any(_eq_blank(a) for a in args)
        case Binary(left=left, right=right):
            return _eq_blank(left) or _eq_blank(right)
        case Unary(operand=operand):
            return _eq_blank(operand)
        case Var(value=value, body=body):
            return _eq_blank(value) or _eq_blank(body)
        case _:
            return False


_DIV_MSG = "Raw '/' division — use DIVIDE(num, den) to absorb zero-denominator errors."
_CONCAT_MSG = "CONCATENATEX plus '&' — pass all parts as CONCATENATEX arguments instead."

_BLANK_MSG = (
    "Compare with ISBLANK(x), not `x = BLANK()` — equality against BLANK is unreliable."
)


def bare_all_table(expr: str) -> str | None:
    """Single-argument ALL(table) used as a filter eraser — REMOVEFILTERS is unambiguous.

    AST-driven: an ALL call whose single argument is a table/column/identifier
    reference; falls back to the legacy regex when the expression does not parse.
    """
    try:
        tree = parse(expr)
    except ParseError:
        if re.search(r"ALL\s*\(\s*'?[A-Za-z_][\w ]*'?\s*\)", expr):
            return _ALL_MSG
        return None
    if _count_calls(tree, "ALL") == 0:
        return None
    # Confirm every ALL site in this tree has exactly one reference argument.
    for node in _walk_calls(tree):
        match node:
            case Call(name="ALL" | "all", args=(arg,)) if isinstance(
                arg, (TableRef, ColumnRef, Ident)
            ):
                return _ALL_MSG
    return None


_ALL_MSG = (
    "Bare ALL(table) — REMOVEFILTERS(table) is clearer when you only want filters gone."
)


def _walk_calls(node: Node) -> Iterator[Call]:
    """Yield every Call node in the tree."""
    match node:
        case Call(_, args):
            yield node
            for a in args:
                yield from _walk_calls(a)
        case Binary(left=left, right=right):
            yield from _walk_calls(left)
            yield from _walk_calls(right)
        case List(items=items):
            for item in items:
                yield from _walk_calls(item)
        case Unary(operand=operand):
            yield from _walk_calls(operand)
        case Var(value=value, body=body):
            yield from _walk_calls(value)
            yield from _walk_calls(body)
        case _:
            return


def _walk_binaries(node: Node) -> Iterator[Binary]:
    """Yield every Binary node in the tree."""
    match node:
        case Call(_, args):
            for a in args:
                yield from _walk_binaries(a)
        case Binary():
            yield node
            yield from _walk_binaries(node.left)
            yield from _walk_binaries(node.right)
        case List(items=items):
            for item in items:
                yield from _walk_binaries(item)
        case Unary(operand=operand):
            yield from _walk_binaries(operand)
        case Var(value=value, body=body):
            yield from _walk_binaries(value)
            yield from _walk_binaries(body)
        case _:
            return


_ABS_MSG = (
    "ABS(...) is never negative — this comparison can never hold. "
    "Check the sign or drop the condition."
)


def abs_negative_comparison(expr: str) -> str | None:
    """`ABS(x) < 0` and friends can never hold: ABS returns a non-negative.

    Flagged always-false shapes — ABS on one side, a numeric literal on
    the other:

    - `ABS(x) < n` with n <= 0
    - `ABS(x) <= n` with n < 0
    - `n > ABS(x)`  with n <= 0
    - `n >= ABS(x)` with n < 0

    The always-true mirrors (`ABS(x) >= 0`) are legitimate defensive
    style and stay unflagged. Unparseable text stays silent.
    """
    try:
        tree = parse(expr)
    except ParseError:
        return None
    for node in _walk_binaries(tree):
        if node.op not in ("<", "<=", ">", ">="):
            continue
        left_value = _numeric_literal(node.left)
        right_value = _numeric_literal(node.right)
        if (
            right_value is not None
            and _is_abs(node.left)
            and _impossible(node.op, right_value, abs_on_left=True)
        ):
            return _ABS_MSG
        if (
            left_value is not None
            and _is_abs(node.right)
            and _impossible(node.op, left_value, abs_on_left=False)
        ):
            return _ABS_MSG
    return None


def _is_abs(node: Node) -> bool:
    """True for a one-argument ABS call — ABS(x) is non-negative for any x."""
    match node:
        case Call(name=name, args=(_arg,)):
            return name.upper() == "ABS"
    return False


def _numeric_literal(node: Node) -> float | None:
    """Value of a (possibly negated) numeric literal; None otherwise."""
    match node:
        case Literal(text=text):
            return _number(text)
        case Unary(op="-" | "−" as sign, operand=Literal(text=text)):
            value = _number(text)
            return -value if value is not None and sign == "-" else None
    return None


def _number(text: str) -> float | None:
    try:
        return float(text)
    except ValueError:
        return None


def _impossible(op: str, bound: float, abs_on_left: bool) -> bool:
    """True when ABS(x) <op> bound is vacuously false for ABS on the side."""
    if abs_on_left:
        return (op == "<" and bound <= 0) or (op == "<=" and bound < 0)
    return (op == ">" and bound <= 0) or (op == ">=" and bound < 0)


def concat_ampersand(expr: str) -> str | None:
    """String concatenation '&' inside CONCATENATEX is redundant.

    AST-driven: any CONCATENATEX call in the tree plus any `Binary('&')`
    anywhere — a `&` inside a string literal is data, not an operator, and
    no longer triggers. Regex fallback when the expression does not parse.
    """
    try:
        tree = parse(expr)
    except ParseError:
        if re.search(r"CONCATENATEX\s*\(", expr, re.IGNORECASE) and "&" in re.sub(
            r'"[^"]*"|\'[^\']*\'', "", expr
        ):
            return _CONCAT_MSG
        return None
    names = {c.name.upper() for c in _walk_calls(tree)}
    if "CONCATENATEX" not in names:
        return None
    if _has_binary(tree, "&"):
        return _CONCAT_MSG
    return None


def _has_binary(node: Node, op: str) -> bool:
    match node:
        case Binary(op=node_op, left=left, right=right):
            return node_op == op or _has_binary(left, op) or _has_binary(right, op)
        case Call(_, args):
            return any(_has_binary(a, op) for a in args)
        case Unary(operand=operand):
            return _has_binary(operand, op)
        case List(items=items):
            return any(_has_binary(item, op) for item in items)
        case Var(value=value, body=body):
            return _has_binary(value, op) or _has_binary(body, op)
        case _:
            return False


_ITER_SUM_MSG = (
    "Row iterator over a single column reference — plain SUM/AVERAGE/COUNT/MIN/MAX "
    "on the column is faster and reads the same."
)

# iterator name -> the plain aggregate that replaces it
_ITER_TO_AGG = {
    "SUMX": "SUM",
    "AVERAGEX": "AVERAGE",
    "COUNTX": "COUNT",
    "MINX": "MIN",
    "MAXX": "MAX",
}


def single_column_iterator(expr: str) -> str | None:
    """`SUMX('Sales', 'Sales'[Amount])` is a plain aggregate in disguise.

    AST-driven: an aggregate iterator whose second argument is exactly the
    fully-qualified form of its (table, column) first argument can collapse
    to the non-iterator aggregate. Unparseable text stays silent.
    """
    try:
        tree = parse(expr)
    except ParseError:
        return None
    for call in _walk_calls(tree):
        match call:
            case Call(name=it_name, args=(TableRef() as table, QualifiedColumn() as col)) if (
                it_name.upper() in _ITER_TO_AGG
                and table.name.replace("'", "") == col.table.replace("'", "")
            ):
                agg = _ITER_TO_AGG[it_name.upper()]
                return (
                    f"{_ITER_SUM_MSG} ({it_name.upper()}({table.name}, {col.table}[{col.name}]) "
                    f"is {agg}({col.table}[{col.name}]).)"
                )
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
    contract (or DIVIDE's third argument) says what you mean.

    AST-driven; regex fallback when the expression does not parse.
    """
    try:
        tree = parse(expr)
    except ParseError:
        if re.search(r"\bIFERROR\s*\(", expr, re.IGNORECASE):
            return _IFERROR_MSG
        return None
    if _has_call(tree, "IFERROR"):
        return _IFERROR_MSG
    return None


_IFERROR_MSG = (
    "IFERROR wraps the whole expression — verify you want silent blank on failure; "
    "prefer DIVIDE's third argument or explicit guards."
)


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
        case List(items=items):
            return max((_iterator_depth(item) for item in items), default=0)
        case Unary(operand=operand):
            return _iterator_depth(operand)
        case Var(value=value, body=body):
            return max(_iterator_depth(value), _iterator_depth(body))
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


_SWITCH_MSG = (
    "SWITCH without a default case returns BLANK silently when no branch matches — "
    "add the final else argument."
)


def switch_missing_default(expr: str) -> str | None:
    """A SWITCH whose argument list holds only value/result pairs falls
    through to BLANK when nothing matches; the optional final argument
    makes the miss explicit.

    With `SWITCH(expr, v1, r1, …, [else])`, an even number of arguments
    after the first means there is no default. Falls back to None when the
    expression does not parse.
    """
    try:
        tree = parse(expr)
    except ParseError:
        return None
    for call in _walk_calls(tree):
        match call:
            case Call(name="SWITCH" | "switch", args=args):
                if len(args) >= 3 and (len(args) - 1) % 2 == 0:
                    return _SWITCH_MSG
    return None


_IF_TRUE_FALSE_MSG = (
    "IF(cond, TRUE(), FALSE()) is just cond — the branch and boolean "
    "coercion add work for the same value."
)

_IF_INVERTED_MSG = (
    "IF(cond, FALSE(), TRUE()) is just NOT cond — the branch buys nothing."
)


def _zero_arg_call(node: Node, name: str) -> bool:
    """True for a `NAME()` call with no arguments."""
    return isinstance(node, Call) and node.name.upper() == name and not node.args


def if_true_false_branches(expr: str) -> str | None:
    """`IF(cond, TRUE(), FALSE())` is `cond`; the branch is pure waste.

    AST-driven: a three-argument IF whose second and third arguments are
    zero-argument TRUE() / FALSE() calls. The inverted order suggests
    `NOT cond`. Bare TRUE/FALSE identifiers, other arities, and nested
    IFs over non-boolean values stay silent. Unparseable text stays silent.
    """
    try:
        tree = parse(expr)
    except ParseError:
        return None
    for call in _walk_calls(tree):
        if call.name.upper() != "IF" or len(call.args) != 3:
            continue
        _, yes, no = call.args
        if _zero_arg_call(yes, "TRUE") and _zero_arg_call(no, "FALSE"):
            return _IF_TRUE_FALSE_MSG
        if _zero_arg_call(yes, "FALSE") and _zero_arg_call(no, "TRUE"):
            return _IF_INVERTED_MSG
    return None


_FILTER_IN_AGG_MSG = (
    "FILTER inside an aggregate builds a filtered table before aggregating — "
    "pass the condition to CALCULATE so the engine can push it into the scan."
)


def filter_inside_aggregate(expr: str) -> str | None:
    """`COUNTROWS(FILTER(…))` / `SUMX(FILTER(…), …)` materialize a table.

    AST-driven: COUNTROWS and the row iterators flag only when their first
    argument is a FILTER call, the shape CALCULATE replaces one-for-one.
    FILTER anywhere else — a CALCULATE filter argument, a nested step, a
    second argument — is a legitimate table expression and stays silent.
    Unparseable text stays silent.
    """
    try:
        tree = parse(expr)
    except ParseError:
        return None
    aggregates = ITERATORS | {"COUNTROWS"}
    for call in _walk_calls(tree):
        if call.name.upper() not in aggregates or not call.args:
            continue
        first = call.args[0]
        if isinstance(first, Call) and first.name.upper() == "FILTER":
            return _FILTER_IN_AGG_MSG
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
    switch_missing_default,
    single_column_iterator,
    abs_negative_comparison,
    if_true_false_branches,
    filter_inside_aggregate,
]
