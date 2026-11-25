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


_BLANK_NOT_EQUAL_MSG = (
    "Compare with NOT(ISBLANK(x)), not `x <> BLANK()` — "
    "inequality against BLANK is just as unreliable as equality."
)


def blank_not_equal(expr: str) -> str | None:
    """`[x] <> BLANK()` is `NOT(ISBLANK([x]))`.

    AST-driven: a `<>` binary with a zero-argument BLANK() call on
    either side — the not-equal twin of rule 4 (`= BLANK()`). Other
    comparisons, other operators, and unparseable text stay silent.
    """
    try:
        tree = parse(expr)
    except ParseError:
        return None
    for binary in _walk_binaries(tree):
        if binary.op != "<>":
            continue
        for side in (binary.left, binary.right):
            if _zero_arg_call(side, "BLANK"):
                return _BLANK_NOT_EQUAL_MSG
    return None


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


def _walk_unaries(node: Node) -> Iterator[Unary]:
    """Yield every Unary node in the tree."""
    match node:
        case Call(_, args):
            for a in args:
                yield from _walk_unaries(a)
        case Binary(left=left, right=right):
            yield from _walk_unaries(left)
            yield from _walk_unaries(right)
        case List(items=items):
            for item in items:
                yield from _walk_unaries(item)
        case Unary():
            yield node
            yield from _walk_unaries(node.operand)
        case Var(value=value, body=body):
            yield from _walk_unaries(value)
            yield from _walk_unaries(body)
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


_NESTED_CALC_MSG = (
    "CALCULATE nested inside CALCULATE — the inner context transition is "
    "redundant; merge the filter lists into a single CALCULATE(...)."
)

_NESTED_CALC_RE = re.compile(r"CALCULATE\s*\(\s*CALCULATE\s*\(", re.IGNORECASE)


def nested_calculate(expr: str) -> str | None:
    """`CALCULATE(CALCULATE(...))`: the inner transition is redundant.

    AST-driven: a CALCULATE call whose first argument is itself a
    CALCULATE flags — the outer call has already transitioned the context,
    so the two filter lists merge into one. Direct nesting only: deeper in
    the expression (behind an iterator, inside an IF branch) the inner
    CALCULATE is either real row-context work rule 1 owns or an ordinary
    conditional. Unparseable text falls back to the literal-token scan.
    """
    try:
        tree = parse(expr)
    except ParseError:
        return _NESTED_CALC_MSG if _NESTED_CALC_RE.search(expr) else None
    for call in _walk_calls(tree):
        if call.name.upper() != "CALCULATE" or not call.args:
            continue
        first = call.args[0]
        if isinstance(first, Call) and first.name.upper() == "CALCULATE":
            return _NESTED_CALC_MSG
    return None


_COUNTROWS_VALUES_MSG = (
    "COUNTROWS(VALUES(col)) over one column — DISTINCTCOUNT(col) returns "
    "the same count without materializing the distinct table."
)

_DISTINCT_ONE_ARG = {"VALUES", "DISTINCT"}


def countrows_values(expr: str) -> str | None:
    """`COUNTROWS(VALUES('T'[Col]))` collapses to `DISTINCTCOUNT('T'[Col])`.

    AST-driven: COUNTROWS whose only argument is a single-column VALUES
    or DISTINCT call — the distinct table exists only to be counted, and
    DISTINCTCOUNT says the intent outright. A table-valued argument —
    `COUNTROWS(VALUES('T'))` — has no DISTINCTCOUNT one-liner and stays
    silent, as does unparseable text: without the AST a column cannot be
    told from a table and the rule must not offer wrong advice.
    """
    try:
        tree = parse(expr)
    except ParseError:
        return None
    for call in _walk_calls(tree):
        if call.name.upper() != "COUNTROWS" or len(call.args) != 1:
            continue
        inner = call.args[0]
        if not isinstance(inner, Call) or inner.name.upper() not in _DISTINCT_ONE_ARG:
            continue
        if len(inner.args) == 1 and isinstance(inner.args[0], (ColumnRef, QualifiedColumn)):
            return _COUNTROWS_VALUES_MSG
    return None


_DISTINCTCOUNT_VALUES_MSG = (
    "DISTINCTCOUNT(VALUES(col)) counts an already-distinct set — "
    "DISTINCTCOUNT(col) says the same thing in one call."
)


def distinctcount_values(expr: str) -> str | None:
    """`DISTINCTCOUNT(VALUES('T'[Col]))` collapses to `DISTINCTCOUNT('T'[Col])`.

    AST-driven: DISTINCTCOUNT whose only argument is a single-column
    VALUES or DISTINCT call — the distinct pass exists only to be
    counted again. A table-valued argument, or an argument that is not
    a bare VALUES/DISTINCT call, stays silent, as does unparseable
    text (without the AST a column cannot be told from a table).
    """
    try:
        tree = parse(expr)
    except ParseError:
        return None
    for call in _walk_calls(tree):
        if call.name.upper() != "DISTINCTCOUNT" or len(call.args) != 1:
            continue
        inner = call.args[0]
        if not isinstance(inner, Call) or inner.name.upper() not in _DISTINCT_ONE_ARG:
            continue
        if len(inner.args) == 1 and isinstance(inner.args[0], (ColumnRef, QualifiedColumn)):
            return _DISTINCTCOUNT_VALUES_MSG
    return None


_IF_ISBLANK_MSG = (
    "IF(ISBLANK(x), y, x) — the blank test and the else value are the "
    "same expression; write COALESCE(x, y) and say it once."
)
_IF_ISBLANK_BLANK_MSG = (
    "IF(ISBLANK(x), BLANK(), x) — the IF returns the tested "
    "expression either way; write x directly."
)
_IF_NOT_ISBLANK_MSG = (
    "IF(NOT(ISBLANK(x)), x, BLANK()) — the IF returns the tested "
    "expression either way; write x directly."
)


def if_isblank_coalesce(expr: str) -> str | None:
    """`IF(ISBLANK(x), y, x)` collapses to `COALESCE(x, y)`.

    AST-driven: a three-argument IF whose condition is a one-argument
    ISBLANK call and whose else-branch equals the tested expression,
    or whose condition is NOT(ISBLANK(t)) and whose yes-branch equals
    the tested expression with a BLANK() else-branch (structural
    dataclass equality). The first shape gets COALESCE(t, y) (or a
    direct "write x" when y is BLANK()); the negated twin gets the
    direct "write x" message. A differing branch (`IF(ISBLANK([A]), 0, [B])`)
    is a genuine conditional and stays silent, as does unparseable text.
    """
    try:
        tree = parse(expr)
    except ParseError:
        return None
    for call in _walk_calls(tree):
        if call.name.upper() != "IF" or len(call.args) != 3:
            continue
        cond, yes, other = call.args
        # `IF(NOT(ISBLANK(x)), x, BLANK())` — the negated twin
        if (
            isinstance(cond, Unary)
            and cond.op.upper() in {"NOT", "!"}
            and isinstance(cond.operand, Call)
            and cond.operand.name.upper() == "ISBLANK"
            and len(cond.operand.args) == 1
            and yes == cond.operand.args[0]
            and _zero_arg_call(other, "BLANK")
        ):
            return _IF_NOT_ISBLANK_MSG
        if (
            isinstance(cond, Call)
            and cond.name.upper() == "ISBLANK"
            and len(cond.args) == 1
            and other == cond.args[0]
        ):
            if _zero_arg_call(yes, "BLANK"):
                # COALESCE(t, BLANK()) is t itself — rule 39 says so
                return _IF_ISBLANK_BLANK_MSG
            return _IF_ISBLANK_MSG
    return None


_SUMMARIZE_EXTRA_MSG = (
    "SUMMARIZE only groups by plain column references — a computed "
    "argument is silently ignored; group first with SUMMARIZE, then "
    "compute with ADDCOLUMNS."
)


def summarize_extra_column(expr: str) -> str | None:
    """`SUMMARIZE('T', [A], [B] + 1)` drops the computed argument.

    AST-driven: every SUMMARIZE argument after the table must be a bare
    `[Col]` or `'T'[Col]` reference. Anything else (an expression, a
    function call, a literal) belongs in a wrapping ADDCOLUMNS over the
    grouped result. Unparseable text stays silent.
    """
    try:
        tree = parse(expr)
    except ParseError:
        return None
    for call in _walk_calls(tree):
        if call.name.upper() != "SUMMARIZE" or len(call.args) < 2:
            continue
        for arg in call.args[1:]:
            if not isinstance(arg, (ColumnRef, QualifiedColumn)):
                return _SUMMARIZE_EXTRA_MSG
    return None


_IF_ISERROR_MSG = (
    "IF(ISERROR(x), y, x) is a hand-rolled IFERROR(x, y) — "
    "one function says it directly."
)


def if_iserror_iferror(expr: str) -> str | None:
    """`IF(ISERROR(x), y, x)` collapses to `IFERROR(x, y)`.

    AST-driven: a three-argument IF whose condition is a one-argument
    ISERROR call and whose else-branch equals the tested expression
    (frozen dataclasses compare structurally). A differing else-branch
    (`IF(ISERROR([A]), 0, [B])`) is a genuine conditional and stays
    silent, as does unparseable text.
    """
    try:
        tree = parse(expr)
    except ParseError:
        return None
    for call in _walk_calls(tree):
        if call.name.upper() != "IF" or len(call.args) != 3:
            continue
        cond, _, other = call.args
        if (
            isinstance(cond, Call)
            and cond.name.upper() == "ISERROR"
            and len(cond.args) == 1
            and other == cond.args[0]
        ):
            return _IF_ISERROR_MSG
    return None


_AND_IN_CALCULATE_MSG = (
    "AND(...) in a CALCULATE filter is one boolean over the current "
    "context — pass each conjunct as its own filter argument; "
    "CALCULATE already ANDs them."
)


def and_in_calculate(expr: str) -> str | None:
    """`CALCULATE(m, AND(a, b))` should be `CALCULATE(m, a, b)`.

    AST-driven: every filter argument (all but the first) of a
    CALCULATE / CALCULATETABLE call that is an `AND(` call or a `&&`
    binary flags. `OR(` / `||` must not be split — splitting would
    change semantics — so they stay silent, as does unparseable text.
    """
    try:
        tree = parse(expr)
    except ParseError:
        return None
    for call in _walk_calls(tree):
        if call.name.upper() not in {"CALCULATE", "CALCULATETABLE"}:
            continue
        for arg in call.args[1:]:
            if isinstance(arg, Call) and arg.name.upper() == "AND":
                return _AND_IN_CALCULATE_MSG
            if isinstance(arg, Binary) and arg.op == "&&":
                return _AND_IN_CALCULATE_MSG
    return None


_UNUSED_VAR_MSG = (
    "VAR {name} is never referenced before RETURN — drop it, or "
    "use it; a dead binding hides the measure's real inputs."
)


def _walk_idents(node: Node) -> Iterator[Ident]:
    """Every bare identifier occurrence in the subtree."""
    if isinstance(node, Ident):
        yield node
    elif isinstance(node, Var):
        yield from _walk_idents(node.value)
        yield from _walk_idents(node.body)
    elif isinstance(node, Call):
        for arg in node.args:
            yield from _walk_idents(arg)
    elif isinstance(node, Binary):
        yield from _walk_idents(node.left)
        yield from _walk_idents(node.right)
    elif isinstance(node, Unary):
        yield from _walk_idents(node.operand)
    elif isinstance(node, List):
        for item in node.items:
            yield from _walk_idents(item)


def unused_variable(expr: str) -> str | None:
    """A `VAR` never referenced before `RETURN` is a dead binding.

    AST-driven: walk the VAR left spine, then for each assignment
    search every later value plus the RETURN body for an identifier
    match (case-insensitive — DAX identifiers are). A variable used by
    a later assignment counts as used. Unparseable text stays silent.
    """
    try:
        tree = parse(expr)
    except ParseError:
        return None
    bindings: list[tuple[str, Node]] = []
    node = tree
    while isinstance(node, Var):
        bindings.append((node.name, node.value))
        node = node.body
    if not bindings:
        return None
    for index, (name, _) in enumerate(bindings):
        later = [value for _, value in bindings[index + 1 :]]
        scope: list[Node] = later + [node]  # later values + the RETURN body
        wanted = name.upper()
        if not any(ident.name.upper() == wanted for n in scope for ident in _walk_idents(n)):
            return _UNUSED_VAR_MSG.format(name=name)
    return None


_COUNTROWS_ZERO_MSG = (
    "COUNTROWS(t) = 0 is ISEMPTY(t) — one call states the emptiness "
    "test directly (<> 0 and > 0 become NOT(ISEMPTY(t)))."
)


def countrows_zero(expr: str) -> str | None:
    """`COUNTROWS(t) = 0` is `ISEMPTY(t)`.

    AST-driven: a COUNTROWS call compared against the numeric literal 0
    with `=`, `<>`, or `>` (either operand order for `=`, COUNTROWS on
    the left for `<>`/`>`, on the right for `0 <`). Comparisons against
    anything other than 0, and COUNTROWS used as a value rather than a
    test, stay silent. Unparseable text stays silent.
    """
    try:
        tree = parse(expr)
    except ParseError:
        return None
    for binary in _walk_binaries(tree):
        if binary.op not in {"=", "<>", ">", "<"}:
            continue
        left, right = binary.left, binary.right
        zero_right = _numeric_literal(right) == 0
        zero_left = _numeric_literal(left) == 0
        if isinstance(left, Call) and left.name.upper() == "COUNTROWS" and len(left.args) == 1 and zero_right and binary.op in {"=", "<>", ">"}:
            return _COUNTROWS_ZERO_MSG
        if isinstance(right, Call) and right.name.upper() == "COUNTROWS" and len(right.args) == 1 and zero_left and binary.op in {"=", "<"}:
            return _COUNTROWS_ZERO_MSG
    return None


_DOUBLE_NEGATION_MSG = (
    "NOT(NOT(x)) is just x — the double wrapper cancels; write the "
    "inner expression directly."
)


def double_negation(expr: str) -> str | None:
    """`NOT(NOT(x))` collapses to `x`.

    AST-driven: NOT parses as a prefix operator, so flag a NOT/!
    Unary whose operand is another NOT/! Unary — mixed spellings
    (`NOT(!x)`) cancel too. Unparseable text stays silent.
    """
    try:
        tree = parse(expr)
    except ParseError:
        return None
    for unary in _walk_unaries(tree):
        if unary.op.upper() not in {"NOT", "!"}:
            continue
        inner = unary.operand
        if isinstance(inner, Unary) and inner.op.upper() in {"NOT", "!"}:
            return _DOUBLE_NEGATION_MSG
    return None


_TRUE_COMPARISON_MSG = (
    "[flag] = TRUE() compares a boolean against TRUE() — the column "
    "is the test; drop the comparison (= FALSE() becomes NOT col)."
)


def true_comparison(expr: str) -> str | None:
    """`[flag] = TRUE()` is `[flag]`; `[flag] = FALSE()` is `NOT [flag]`.

    AST-driven: an `=`/`<>` binary with a zero-argument TRUE() or
    FALSE() call on either side. A TRUE()/FALSE() in any other position
    (an IF branch, say) is not this pattern, and neither is a bare
    `TRUE` identifier. Unparseable text stays silent.
    """
    try:
        tree = parse(expr)
    except ParseError:
        return None
    for binary in _walk_binaries(tree):
        if binary.op not in {"=", "<>"}:
            continue
        for side in (binary.left, binary.right):
            if _zero_arg_call(side, "TRUE") or _zero_arg_call(side, "FALSE"):
                return _TRUE_COMPARISON_MSG
    return None


_IF_SAME_BRANCHES_MSG = (
    "IF(cond, x, x) returns the same value either way — the condition "
    "computes for nothing; write x directly."
)


def _canonical(node: Node) -> object:
    """Hashable shape of a subtree with DAX's case rules folded in.

    DAX identifiers (columns, tables, variables, function names) are
    case-insensitive, so `[X] * 2` and `[x] * 2` are the same branch.
    String literals keep their case; numbers compare by value, so
    `2` and `2.0` match.
    """
    if isinstance(node, Literal):
        value = _number(node.text)
        return ("lit", value) if value is not None else ("lit", node.text)
    if isinstance(node, ColumnRef):
        return ("col", node.name.upper())
    if isinstance(node, QualifiedColumn):
        return ("qcol", node.table.upper(), node.name.upper())
    if isinstance(node, TableRef):
        return ("table", node.name.upper())
    if isinstance(node, Ident):
        return ("ident", node.name.upper())
    if isinstance(node, Call):
        return ("call", node.name.upper(), tuple(_canonical(a) for a in node.args))
    if isinstance(node, Binary):
        return ("bin", node.op, _canonical(node.left), _canonical(node.right))
    if isinstance(node, List):
        return ("list", tuple(_canonical(i) for i in node.items))
    if isinstance(node, Unary):
        return ("unary", node.op.upper(), _canonical(node.operand))
    if isinstance(node, Var):
        return ("var", node.name.upper(), _canonical(node.value), _canonical(node.body))
    return ("unknown",)


def if_same_branches(expr: str) -> str | None:
    """`IF(cond, x, x)` is `x` — the predicate computes for nothing.

    AST-driven: a three-argument IF whose last two arguments have the
    same shape, compared case-insensitively (`[X] * 2` ≡ `[x] * 2`) and
    by numeric value (`2` ≡ `2.0`). Only AST-equal branches collapse —
    branches that are merely textually similar stay silent, as does
    unparseable text.
    """
    try:
        tree = parse(expr)
    except ParseError:
        return None
    for call in _walk_calls(tree):
        if call.name.upper() != "IF" or len(call.args) != 3:
            continue
        yes, no = call.args[1], call.args[2]
        if _canonical(yes) == _canonical(no):
            return _IF_SAME_BRANCHES_MSG
    return None


_NESTED_SAME_PREDICATE_MSG = (
    "IF(c, … IF(c, …) …) — the inner condition is implied by the "
    "outer one; collapse the nesting."
)


def nested_same_predicate(expr: str) -> str | None:
    """`IF(c, IF(c, a, b), d)` is `IF(c, a, d)`; same for the else branch.

    AST-driven: a three-argument IF whose second or third argument
    is another three-argument IF with a canonically equal predicate
    (the rule 29 signature — identifiers fold case, numbers compare
    by value). In the true-branch case the inner c is known true (the
    outer picked it), so the inner IF reduces to its true branch; in
    the else branch it is known false, so it reduces to its final
    argument. Deeper nesting and unparseable text stay silent.
    """
    try:
        tree = parse(expr)
    except ParseError:
        return None
    for call in _walk_calls(tree):
        if call.name.upper() != "IF" or len(call.args) != 3:
            continue
        predicate = _canonical(call.args[0])
        for index in (1, 2):
            inner = call.args[index]
            if (
                isinstance(inner, Call)
                and inner.name.upper() == "IF"
                and len(inner.args) == 3
                and _canonical(inner.args[0]) == predicate
            ):
                return _NESTED_SAME_PREDICATE_MSG
    return None


_COALESCE_TRAILING_BLANK_MSG = (
    "COALESCE with a trailing BLANK() adds nothing — the shorter "
    "COALESCE(a, …) says the same thing."
)
_COALESCE_SINGLE_ARG_MSG = (
    "COALESCE(x) is just x — one argument, no fallback, no call."
)


def coalesce_trailing_blank(expr: str) -> str | None:
    """`COALESCE(..., BLANK())` drops the trailing default; `COALESCE(x)` is `x`.

    AST-driven: a single-argument COALESCE, or a zero-argument
    BLANK() call in the LAST argument position. A middle BLANK()
    (`COALESCE([x], BLANK(), [y])`) short-circuits to blank and hides
    later arguments from evaluation, which is meaningful — silent, as
    is unparseable text.
    """
    try:
        tree = parse(expr)
    except ParseError:
        return None
    for call in _walk_calls(tree):
        if call.name.upper() != "COALESCE":
            continue
        if len(call.args) == 1:
            return _COALESCE_SINGLE_ARG_MSG
        if _zero_arg_call(call.args[-1], "BLANK"):
            return _COALESCE_TRAILING_BLANK_MSG
    return None


_DUPLICATE_COALESCE_MSG = (
    "COALESCE(x, …, x) — a duplicate argument is unreachable (the "
    "first non-blank wins earlier); drop it."
)


def duplicate_coalesce(expr: str) -> str | None:
    """`COALESCE(x, …, x)` — a repeated later argument is unreachable.

    AST-driven: a COALESCE call with two arguments that share a
    canonical subtree signature (identifiers fold case, numbers
    compare by value). The first occurrence wins; every later copy
    is dead weight. Single-argument calls and unparseable text stay
    silent.
    """
    try:
        tree = parse(expr)
    except ParseError:
        return None
    for call in _walk_calls(tree):
        if call.name.upper() != "COALESCE" or len(call.args) < 2:
            continue
        seen: set[object] = set()
        repeated = False
        for arg in call.args:
            signature = _canonical(arg)
            if signature in seen:
                repeated = True
                break
            seen.add(signature)
        if repeated:
            return _DUPLICATE_COALESCE_MSG
    return None


_DUPLICATE_BOOLEAN_MSG = (
    "{op} with identical operands — the duplicate adds nothing; "
    "keep one."
)


def duplicate_boolean_operand(expr: str) -> str | None:
    """`c && c` is `c`; same for `||`, `AND(c, c)` and `OR(c, c)`.

    AST-driven: an `AND(`/`OR(` call or `&&`/`||` binary with two
    canonically equal operands. The signature is rule 29's (idents
    fold case, numbers compare by value). Absorption by a constant
    (`TRUE()`/`FALSE()`) is rule 38's territory and is not re-flagged
    here; non-equal operands stay silent, as does unparseable text.
    """
    try:
        tree = parse(expr)
    except ParseError:
        return None
    for call in _walk_calls(tree):
        if call.name.upper() not in {"AND", "OR"}:
            continue
        seen: set[object] = set()
        for arg in call.args:
            signature = _canonical(arg)
            if signature in seen:
                return _DUPLICATE_BOOLEAN_MSG.format(op=call.name.upper())
            seen.add(signature)
    for binary in _walk_binaries(tree):
        if binary.op in {"&&", "||"} and _canonical(binary.left) == _canonical(binary.right):
            return _DUPLICATE_BOOLEAN_MSG.format(op=binary.op)
    return None


_INDICATOR_SUM_MSG = (
    "SUMX over IF(cond, 1, 0) counts passing rows — "
    "COUNTROWS(FILTER(t, cond)) says the same thing without the loop."
)


def indicator_sum(expr: str) -> str | None:
    """`SUMX(t, IF(c, 1, 0))` is `COUNTROWS(FILTER(t, c))`.

    AST-driven: a SUMX call whose second argument is a three-argument
    IF whose last two arguments are the numeric literals 1 and 0 (in
    that order; the inverted `IF(c, 0, 1)` reads as "failing rows"
    and stays silent). Expressions, non-numeric branches and
    unparseable text stay silent.
    """
    try:
        tree = parse(expr)
    except ParseError:
        return None
    for call in _walk_calls(tree):
        if call.name.upper() != "SUMX" or len(call.args) != 2:
            continue
        inner = call.args[1]
        if not isinstance(inner, Call) or inner.name.upper() != "IF" or len(inner.args) != 3:
            continue
        yes, no = inner.args[1], inner.args[2]
        if _numeric_literal(yes) == 1 and _numeric_literal(no) == 0:
            return _INDICATOR_SUM_MSG
    return None


_CONSTANT_CONDITION_MSG = (
    "IF({cond}(), x, y) — the condition is a constant; the {branch} "
    "branch always runs; drop the dead branch and the call."
)


def constant_condition(expr: str) -> str | None:
    """`IF(TRUE(), x, y)` is `x`; `IF(FALSE(), x, y)` is `y`.

    AST-driven: a three-argument IF whose condition is a zero-argument
    TRUE() or FALSE() call — the other branch is unreachable code.
    Non-constant conditions stay silent, as does unparseable text.
    """
    try:
        tree = parse(expr)
    except ParseError:
        return None
    for call in _walk_calls(tree):
        if call.name.upper() != "IF" or len(call.args) != 3:
            continue
        if _zero_arg_call(call.args[0], "TRUE"):
            return _CONSTANT_CONDITION_MSG.format(cond="TRUE", branch="first")
        if _zero_arg_call(call.args[0], "FALSE"):
            return _CONSTANT_CONDITION_MSG.format(cond="FALSE", branch="else")
    return None


_ABSORBED_OR_MSG = (
    "OR(TRUE(), x) is TRUE() — TRUE absorbs every other operand; "
    "drop the rest."
)
_ABSORBED_AND_MSG = (
    "AND(FALSE(), x) is FALSE() — FALSE absorbs every other "
    "operand; drop the rest."
)


def absorbed_boolean(expr: str) -> str | None:
    """`OR(TRUE(), x)` is `TRUE()`; `AND(FALSE(), x)` is `FALSE()`.

    AST-driven: an OR call or || binary with a zero-argument TRUE()
    call anywhere (OR), or an AND call or && binary with a
    zero-argument FALSE() call anywhere (AND) — the constant absorbs
    every other operand. The identity pair (OR(FALSE(), x) ≡ x,
    AND(TRUE(), x) ≡ x) is not flagged here; unparseable text stays
    silent.
    """
    try:
        tree = parse(expr)
    except ParseError:
        return None
    for call in _walk_calls(tree):
        name = call.name.upper()
        if name == "OR" and any(_zero_arg_call(a, "TRUE") for a in call.args):
            return _ABSORBED_OR_MSG
        if name == "AND" and any(_zero_arg_call(a, "FALSE") for a in call.args):
            return _ABSORBED_AND_MSG
    for binary in _walk_binaries(tree):
        if binary.op == "||" and (
            _zero_arg_call(binary.left, "TRUE") or _zero_arg_call(binary.right, "TRUE")
        ):
            return _ABSORBED_OR_MSG
        elif binary.op == "&&" and (
            _zero_arg_call(binary.left, "FALSE") or _zero_arg_call(binary.right, "FALSE")
        ):
            return _ABSORBED_AND_MSG
    return None


_POWER_ONE_MSG = (
    "POWER(x, 1) returns the base — write x directly."
)
_POWER_ZERO_MSG = (
    "POWER(x, 0) returns 1 — write the literal."
)
_CARET_ONE_MSG = (
    "x ^ 1 returns the base — write x directly."
)
_CARET_ZERO_MSG = (
    "x ^ 0 returns 1 — write the literal."
)


def power_identity(expr: str) -> str | None:
    """`POWER(x, 1)` and `x ^ 1` are `x`; the zero-exponent twins are `1`.

    AST-driven: a POWER call whose second argument is a (possibly
    negated) numeric literal equal to 1 or 0, or a `^` binary with a
    numeric literal exponent equal to 1 or 0 (exponent on the right
    side only). `^` is right-associative with tighter precedence than
    unary minus. `POWER(x, 2)` and `x ^ 2` are real work; non-literal
    exponents stay silent, as does unparseable text.
    """
    try:
        tree = parse(expr)
    except ParseError:
        return None
    for call in _walk_calls(tree):
        if call.name.upper() != "POWER" or len(call.args) != 2:
            continue
        exponent = _numeric_literal(call.args[1])
        if exponent == 1:
            return _POWER_ONE_MSG
        if exponent == 0:
            return _POWER_ZERO_MSG
    for binary in _walk_binaries(tree):
        if binary.op != "^":
            continue
        exponent = _numeric_literal(binary.right)
        if exponent == 1:
            return _CARET_ONE_MSG
        if exponent == 0:
            return _CARET_ZERO_MSG
    return None


_COUNTX_CONSTANT_MSG = (
    "{name}(t, k) with a constant k counts every row — "
    "COUNTROWS(t) says the same thing with no loop."
)


def countx_constant(expr: str) -> str | None:
    """`COUNTX(t, k)` (or `COUNTAX(t, k)`) with numeric literal k is `COUNTROWS(t)`.

    AST-driven: a COUNTX or COUNTAX call whose second argument is a
    (possibly negated) numeric literal — a constant is never blank, so
    every row counts. Expressions and unparseable text stay silent.
    """
    try:
        tree = parse(expr)
    except ParseError:
        return None
    for call in _walk_calls(tree):
        name = call.name.upper()
        if name not in {"COUNTX", "COUNTAX"} or len(call.args) != 2:
            continue
        if _numeric_literal(call.args[1]) is not None:
            return _COUNTX_CONSTANT_MSG.format(name=name)
    return None


_SUMX_CONSTANT_MSG = (
    "SUMX(t, k) with a constant k sums the same number per row — "
    "COUNTROWS(t) * k counts the rows without the loop "
    "(just COUNTROWS(t) for k = 1)."
)


def sumx_constant(expr: str) -> str | None:
    """`SUMX(t, k)` with a numeric literal k is `COUNTROWS(t) * k`.

    AST-driven: a SUMX call whose second argument is a (possibly
    negated) numeric literal. SUMX is the only iterator where the
    collapse holds on empty tables (0 = 0); AVERAGEX/MAXX return
    BLANK there, so they stay silent. An expression k, an unparseable
    text — all silent.
    """
    try:
        tree = parse(expr)
    except ParseError:
        return None
    for call in _walk_calls(tree):
        if call.name.upper() != "SUMX" or len(call.args) != 2:
            continue
        if _numeric_literal(call.args[1]) is not None:
            return _SUMX_CONSTANT_MSG
    return None


_TRIM_NESTED_MSG = (
    "TRIM(TRIM(x)) — TRIM is idempotent; one call trims everything "
    "the nested pair can."
)


def trim_nested(expr: str) -> str | None:
    """`TRIM(TRIM(x))` collapses to `TRIM(x)`.

    AST-driven: a TRIM call whose single argument is another TRIM
    call. Wrapped forms like `TRIM(LOWER(TRIM(x)))` and single TRIMs
    stay silent, as does unparseable text.
    """
    try:
        tree = parse(expr)
    except ParseError:
        return None
    for call in _walk_calls(tree):
        if call.name.upper() != "TRIM" or len(call.args) != 1:
            continue
        inner = call.args[0]
        if isinstance(inner, Call) and inner.name.upper() == "TRIM" and len(inner.args) == 1:
            return _TRIM_NESTED_MSG
    return None


_FILTER_TRUE_MSG = (
    "FILTER(t, TRUE()) passes every row — the table is the filter; "
    "write t instead of the iterator."
)


def filter_true(expr: str) -> str | None:
    """`FILTER(t, TRUE())` is `t`.

    AST-driven: a FILTER call whose second argument is a zero-argument
    TRUE() call. FALSE() has no one-call replacement (there is no
    empty-table literal in DAX) and stays silent, as do bare TRUE
    identifiers and non-literal second arguments, and unparseable text.
    """
    try:
        tree = parse(expr)
    except ParseError:
        return None
    for call in _walk_calls(tree):
        if call.name.upper() != "FILTER" or len(call.args) != 2:
            continue
        if _zero_arg_call(call.args[1], "TRUE"):
            return _FILTER_TRUE_MSG
    return None


_IDENTITY_ARITHMETIC_MSG = (
    "Identity arithmetic — x * 1, 1 * x, x / 1 all hold for blanks "
    "and non-blanks alike; drop the operation."
)


def identity_arithmetic(expr: str) -> str | None:
    """`x * 1`, `1 * x` and `x / 1` return x — even for blanks.

    AST-driven: a binary `*` or `/` with the numeric literal 1 on the
    identity side (`* 1` either side, `/ 1` on the right only). BLANKs
    propagate in multiplication and division, so these hold for every
    value. Additive zero is deliberately NOT flagged: BLANK converts
    to 0 in sums and subtractions, so `x + 0` is the documented idiom
    to display blank measures as zeros — dropping the operation would
    remove those zeros from visuals.
    """
    try:
        tree = parse(expr)
    except ParseError:
        return None
    for binary in _walk_binaries(tree):
        left = _numeric_literal(binary.left)
        right = _numeric_literal(binary.right)
        match binary.op:
            case "*":
                if left == 1 or right == 1:
                    return _IDENTITY_ARITHMETIC_MSG
            case "/":
                if right == 1:
                    return _IDENTITY_ARITHMETIC_MSG
    return None


def rule_summary(rule: Rule) -> str:
    """First sentence of a rule's docstring, for rule inventories."""
    text = " ".join((rule.__doc__ or "").strip().splitlines())
    return text.partition(". ")[0]


_IDEMPOTENT_NESTED = frozenset({"UPPER", "LOWER", "ABS", "INT"})

_IDEMPOTENT_NESTED_MSG = (
    "{name}({name}(x)) — {name} is idempotent; one call does what "
    "the pair can."
)


def idempotent_nested(expr: str) -> str | None:
    """`UPPER(UPPER(x))` is `UPPER(x)` — same for LOWER, ABS, INT.

    AST-driven: a single-argument call whose argument is the same
    function. Exact idempotents only — TRIM has rule 32, mixed pairs
    like `UPPER(LOWER(x))` compose rather than cancel, and everything
    else stays silent, as does unparseable text.
    """
    try:
        tree = parse(expr)
    except ParseError:
        return None
    for call in _walk_calls(tree):
        name = call.name.upper()
        if name not in _IDEMPOTENT_NESTED or len(call.args) != 1:
            continue
        inner = call.args[0]
        if isinstance(inner, Call) and inner.name.upper() == name and len(inner.args) == 1:
            return _IDEMPOTENT_NESTED_MSG.format(name=name)
    return None


_COMPLEMENTARY_LOGIC_MSG = (
    "x OR NOT(x) is TRUE() and x AND NOT(x) is FALSE() — the "
    "complementary operands always win."
)


def complementary_logic(expr: str) -> str | None:
    """`x || NOT(x)` is TRUE; `x && NOT(x)` is FALSE.

    AST-driven: a `||`/`&&` binary or an `OR(`/`AND(` call whose two
    operands are complements under the canonical signature — one is a
    NOT/! unary over the other. BLANK coerces to FALSE in boolean
    context, so the collapse holds for every boolean value.
    """
    try:
        tree = parse(expr)
    except ParseError:
        return None

    def complements(a: Node, b: Node) -> bool:
        if isinstance(a, Unary) and a.op.upper() in {"NOT", "!"}:
            return _canonical(a.operand) == _canonical(b)
        if isinstance(b, Unary) and b.op.upper() in {"NOT", "!"}:
            return _canonical(b.operand) == _canonical(a)
        return False

    for binary in _walk_binaries(tree):
        if binary.op in {"||", "&&"} and complements(binary.left, binary.right):
            return _COMPLEMENTARY_LOGIC_MSG
    for call in _walk_calls(tree):
        name = call.name.upper()
        if name in {"OR", "AND"} and len(call.args) == 2 and complements(call.args[0], call.args[1]):
            return _COMPLEMENTARY_LOGIC_MSG
    return None


_ZERO_DIVISOR_MSG = (
    "DIVIDE(x, 0) always returns BLANK — drop the call, or use its "
    "alternate result directly."
)
_ZERO_DIVISOR_ALT_MSG = (
    "DIVIDE(x, 0, alt) always returns alt — one as a denominator is "
    "impossible here; write the alternate directly."
)


def zero_divisor(expr: str) -> str | None:
    """`DIVIDE(x, 0)` has no real division to perform.

    AST-driven: a DIVIDE call whose second argument is a (possibly
    negated) numeric literal 0. A constant non-zero denominator and a
    column denominator both vary the result or are legitimate, and
    stay silent.
    """
    try:
        tree = parse(expr)
    except ParseError:
        return None
    for call in _walk_calls(tree):
        if call.name.upper() != "DIVIDE" or len(call.args) < 2:
            continue
        if _numeric_literal(call.args[1]) == 0:
            if len(call.args) >= 3:
                return _ZERO_DIVISOR_ALT_MSG
            return _ZERO_DIVISOR_MSG
    return None


_SELF_COMPARISON_MSG = (
    "x = x is TRUE() and x <> x is FALSE() — comparing an expression "
    "to itself gives a constant."
)


def self_comparison(expr: str) -> str | None:
    """`[x] = [x]` is TRUE; `[x] <> [x]` is FALSE.

    AST-driven: an `=` or `<>` binary whose operands are both bare
    column references or identifiers and share a canonical signature.
    Limited to bare refs so expressions with side effects or volatile
    functions are never claimed constant.
    """
    try:
        tree = parse(expr)
    except ParseError:
        return None
    bare = (ColumnRef, Ident, QualifiedColumn)
    for binary in _walk_binaries(tree):
        if binary.op not in {"=", "<>"}:
            continue
        if (
            isinstance(binary.left, bare)
            and isinstance(binary.right, bare)
            and _canonical(binary.left) == _canonical(binary.right)
        ):
            return _SELF_COMPARISON_MSG
    return None


_SELF_SUBTRACTION_MSG = (
    "x - x is 0 — subtracting a value from itself has no result worth "
    "computing."
)


def self_subtraction(expr: str) -> str | None:
    """`[x] - [x]` is 0, including for blanks (BLANK converts to 0).

    AST-driven: a `-` binary whose operands are both bare column
    references or identifiers and share a canonical signature. Calls
    and arithmetic expressions are not claimed constant.
    """
    try:
        tree = parse(expr)
    except ParseError:
        return None
    bare = (ColumnRef, Ident, QualifiedColumn)
    for binary in _walk_binaries(tree):
        if binary.op != "-":
            continue
        if (
            isinstance(binary.left, bare)
            and isinstance(binary.right, bare)
            and _canonical(binary.left) == _canonical(binary.right)
        ):
            return _SELF_SUBTRACTION_MSG
    return None


_TRIVIAL_VAR_MSG = (
    "VAR {name} = value RETURN {name} is just value — the binding "
    "adds nothing."
)


def _walk_vars(node: Node) -> Iterator[Var]:
    """Every Var node in the tree, including ones inside other nodes."""
    if isinstance(node, Var):
        yield node
        yield from _walk_vars(node.value)
        yield from _walk_vars(node.body)
    elif isinstance(node, Call):
        for arg in node.args:
            yield from _walk_vars(arg)
    elif isinstance(node, Binary):
        yield from _walk_vars(node.left)
        yield from _walk_vars(node.right)
    elif isinstance(node, Unary):
        yield from _walk_vars(node.operand)
    elif isinstance(node, List):
        for item in node.items:
            yield from _walk_vars(item)


def trivial_var(expr: str) -> str | None:
    """`VAR a = value RETURN a` is `value`.

    AST-driven: a Var node whose body is a bare identifier matching the
    binding name (case-insensitive) and not another Var binding. The
    value is evaluated at the same row context either way, so the
    rewrite is exact.
    """
    try:
        tree = parse(expr)
    except ParseError:
        return None
    for var in _walk_vars(tree):
        if (
            isinstance(var.body, Ident)
            and var.body.name.upper() == var.name.upper()
        ):
            return _TRIVIAL_VAR_MSG.format(name=var.name)
    return None


_DUPLICATE_MINMAX_MSG = (
    "{name}(x, x) returns x — the second argument is a duplicate."
)


def duplicate_minmax(expr: str) -> str | None:
    """`MIN(x, x)` and `MAX(x, x)` are `x`, including for blanks.

    AST-driven: a two-argument MIN or MAX call whose arguments share a
    canonical subtree signature. Calls with different arguments, and
    more than two arguments, stay silent.
    """
    try:
        tree = parse(expr)
    except ParseError:
        return None
    for call in _walk_calls(tree):
        name = call.name.upper()
        if name not in {"MIN", "MAX"} or len(call.args) != 2:
            continue
        if _canonical(call.args[0]) == _canonical(call.args[1]):
            return _DUPLICATE_MINMAX_MSG.format(name=name)
    return None


_NOT_CONSTANT_MSG = (
    "NOT({name}) is {value} — the operand is a constant."
)


def not_constant(expr: str) -> str | None:
    """NOT over a zero-argument logical constant folds to a constant.

    AST-driven: a NOT/! unary whose operand is a zero-argument TRUE(),
    FALSE() or BLANK() call. NOT(BLANK()) is TRUE because BLANK behaves
    as FALSE in a boolean context. NOT over a column or expression
    stays silent.
    """
    try:
        tree = parse(expr)
    except ParseError:
        return None
    constants = {"TRUE": "FALSE", "FALSE": "TRUE", "BLANK": "TRUE"}
    for unary in _walk_unaries(tree):
        if unary.op.upper() not in {"NOT", "!"}:
            continue
        if not isinstance(unary.operand, Call) or unary.operand.args:
            continue
        name = unary.operand.name.upper()
        if name in constants:
            return _NOT_CONSTANT_MSG.format(name=name, value=constants[name])
    return None


_SELECTEDVALUE_BLANK_DEFAULT_MSG = (
    "SELECTEDVALUE(t, BLANK()) already defaults to BLANK — drop the "
    "second argument."
)


def selectedvalue_blank_default(expr: str) -> str | None:
    """A BLANK() fallback to SELECTEDVALUE is its existing default.

    AST-driven: a SELECTEDVALUE call with exactly two arguments whose
    second is a zero-argument BLANK() call. Other fallbacks are
    meaningful and stay silent.
    """
    try:
        tree = parse(expr)
    except ParseError:
        return None
    for call in _walk_calls(tree):
        if call.name.upper() != "SELECTEDVALUE" or len(call.args) != 2:
            continue
        if _zero_arg_call(call.args[1], "BLANK"):
            return _SELECTEDVALUE_BLANK_DEFAULT_MSG
    return None


_IF_SWITCH_MSG = (
    "IF(x = k1, a, IF(x = k2, b, c)) is SWITCH(x, k1, a, k2, b, c) — "
    "one lookup instead of repeated comparisons."
)


def if_switch(expr: str) -> str | None:
    """Nested equality IFs on the same column form a SWITCH lookup.

    AST-driven: a three-argument IF whose condition is `=` between a
    bare column/identifier and a literal, and whose else-branch is an
    IF with the same tested expression and a different literal. Only
    one nesting level is required to flag; deeper chains report once.
    """
    try:
        tree = parse(expr)
    except ParseError:
        return None
    bare = (ColumnRef, Ident, QualifiedColumn)
    for outer in _walk_calls(tree):
        if outer.name.upper() != "IF" or len(outer.args) != 3:
            continue
        cond, _, otherwise = outer.args
        if not isinstance(cond, Binary) or cond.op != "=":
            continue
        if not isinstance(cond.left, bare) or not isinstance(cond.right, Literal):
            continue
        if not isinstance(otherwise, Call) or otherwise.name.upper() != "IF" or len(otherwise.args) != 3:
            continue
        inner = otherwise.args[0]
        if not isinstance(inner, Binary) or inner.op != "=":
            continue
        if _canonical(inner.left) != _canonical(cond.left):
            continue
        if not isinstance(inner.right, Literal) or _canonical(inner.right) == _canonical(cond.right):
            continue
        return _IF_SWITCH_MSG
    return None


_COUNTROWS_FALSE_FILTER_MSG = (
    "COUNTROWS(FILTER(t, FALSE())) is 0 — the filter returns no rows."
)


def countrows_false_filter(expr: str) -> str | None:
    """Counting a FALSE-filtered table always yields the literal 0.

    AST-driven: COUNTROWS whose single argument is a FILTER call with
    a zero-argument FALSE() call as its condition. TRUE() filters are
    the separate `FILTER(t, TRUE())` rule's territory.
    """
    try:
        tree = parse(expr)
    except ParseError:
        return None
    for call in _walk_calls(tree):
        if call.name.upper() != "COUNTROWS" or len(call.args) != 1:
            continue
        inner = call.args[0]
        if (
            isinstance(inner, Call)
            and inner.name.upper() == "FILTER"
            and len(inner.args) == 2
            and _zero_arg_call(inner.args[1], "FALSE")
        ):
            return _COUNTROWS_FALSE_FILTER_MSG
    return None


_NESTED_NEGATED_PREDICATE_MSG = (
    "IF(c, IF(NOT(c), a, b), d) is IF(c, b, d) — the inner condition "
    "is decided by the outer branch."
)


def nested_negated_predicate(expr: str) -> str | None:
    """A branch-nested IF whose predicate is NOT of the outer one collapses.

    AST-driven: an outer three-argument IF whose condition canonically
    matches the operand of a NOT/! unary used as the condition of an IF
    in either direct branch. BLANK takes the false branch, so the
    reduction holds there too.
    """
    try:
        tree = parse(expr)
    except ParseError:
        return None
    for outer in _walk_calls(tree):
        if outer.name.upper() != "IF" or len(outer.args) != 3:
            continue
        condition = _canonical(outer.args[0])
        for index in (1, 2):
            inner = outer.args[index]
            if not isinstance(inner, Call) or inner.name.upper() != "IF" or len(inner.args) != 3:
                continue
            pred = inner.args[0]
            if not isinstance(pred, Unary) or pred.op.upper() not in {"NOT", "!"}:
                continue
            if _canonical(pred.operand) == condition:
                return _NESTED_NEGATED_PREDICATE_MSG
    return None


_DIVIDE_BY_ONE_MSG = (
    "DIVIDE(x, 1) returns x — one as a denominator changes nothing."
)
_DIVIDE_BY_ONE_ALT_MSG = (
    "DIVIDE(x, 1, alt) returns x — a denominator of 1 never triggers "
    "the alternate; drop both extra arguments."
)


def divide_by_one(expr: str) -> str | None:
    """`DIVIDE(x, 1)` is `x`, BLANK included.

    AST-driven: a DIVIDE call whose second argument is a numeric literal
    1. The three-argument alternate form is also equivalent because a
    denominator of 1 never triggers the alternate. Other denominators
    stay silent.
    """
    try:
        tree = parse(expr)
    except ParseError:
        return None
    for call in _walk_calls(tree):
        if call.name.upper() != "DIVIDE" or len(call.args) < 2:
            continue
        if _numeric_literal(call.args[1]) == 1:
            if len(call.args) >= 3:
                return _DIVIDE_BY_ONE_ALT_MSG
            return _DIVIDE_BY_ONE_MSG
    return None


_REPEATED_ROUND_MSG = (
    "{name}({name}(x, n), n) is {name}(x, n) — rounding twice to the "
    "same precision does nothing the first call didn't."
)


def repeated_round(expr: str) -> str | None:
    """ROUND(ROUND(x, n), n) is ROUND(x, n).

    AST-driven: a two-argument ROUND call whose first argument is
    another ROUND call with the same digits argument under the canonical
    signature. Different precisions stay silent.
    """
    try:
        tree = parse(expr)
    except ParseError:
        return None
    for call in _walk_calls(tree):
        if call.name.upper() != "ROUND" or len(call.args) != 2:
            continue
        inner = call.args[0]
        if not isinstance(inner, Call) or inner.name.upper() != "ROUND" or len(inner.args) != 2:
            continue
        if _canonical(inner.args[1]) == _canonical(call.args[1]):
            return _REPEATED_ROUND_MSG.format(name=call.name.upper())
    return None


_CONCATENATE_TWO_ARGS_MSG = (
    "CONCATENATE(a, b) is a & b — the operator says the same thing."
)


def concatenate_two_args(expr: str) -> str | None:
    """Two-argument CONCATENATE is `&` with the same operands.

    AST-driven: a CONCATENATE call with exactly two arguments. Both
    forms coerce their operands to text, including BLANK. Nested
    CONCATENATE calls with more than two arguments are out of scope.
    """
    try:
        tree = parse(expr)
    except ParseError:
        return None
    for call in _walk_calls(tree):
        if call.name.upper() == "CONCATENATE" and len(call.args) == 2:
            return _CONCATENATE_TWO_ARGS_MSG
    return None


_EMPTY_IN_MSG = (
    "x IN {} is always FALSE — an empty list has no members to match."
)


def empty_in(expr: str) -> str | None:
    """`[x] IN {}` is FALSE for every value, BLANK included.

    AST-driven: an IN binary whose right operand is a List node with no
    items. A non-empty list, or a right operand that is not a list at
    all, stays silent.
    """
    try:
        tree = parse(expr)
    except ParseError:
        return None
    for binary in _walk_binaries(tree):
        if binary.op == "IN" and isinstance(binary.right, List) and not binary.right.items:
            return _EMPTY_IN_MSG
    return None


_LITERAL_CONDITION_MSG = (
    "IF({lhs} {op} {rhs}, x, y) — the condition is a comparison of "
    "literal numbers, so it always returns the same branch."
)


def literal_condition(expr: str) -> str | None:
    """An IF whose condition compares two numeric literals is constant.

    AST-driven: a three-argument IF whose condition is a comparison
    binary (`=`, `<>`, `<`, `>`, `<=`, `>=`) with numeric literals on
    both sides. Conditions involving columns, calls or any other
    operators stay silent, as does unparseable text.
    """
    try:
        tree = parse(expr)
    except ParseError:
        return None
    ops = {"=", "<>", "<", ">", "<=", ">="}
    for call in _walk_calls(tree):
        if call.name.upper() != "IF" or len(call.args) != 3:
            continue
        cond = call.args[0]
        if not isinstance(cond, Binary) or cond.op not in ops:
            continue
        lhs, rhs = _numeric_literal(cond.left), _numeric_literal(cond.right)
        if lhs is None or rhs is None:
            continue
        return _LITERAL_CONDITION_MSG.format(lhs=lhs, op=cond.op, rhs=rhs)
    return None


_COALESCE_LEADING_BLANK_MSG = (
    "COALESCE ignores leading BLANK() arguments — drop them."
)


def coalesce_leading_blank(expr: str) -> str | None:
    """A leading BLANK() in COALESCE is always skipped.

    AST-driven: a COALESCE call whose first argument is a zero-argument
    BLANK() call. The trailing and single-argument forms belong to the
    existing `coalesce_trailing_blank` rule.
    """
    try:
        tree = parse(expr)
    except ParseError:
        return None
    for call in _walk_calls(tree):
        if call.name.upper() != "COALESCE" or not call.args:
            continue
        if _zero_arg_call(call.args[0], "BLANK"):
            return _COALESCE_LEADING_BLANK_MSG
    return None


_SWITCH_CONSTANT_FIRST_CASE_MSG = (
    "SWITCH(TRUE(), TRUE(), x, ...) always takes the first case — "
    "write x directly."
)


def switch_constant_first_case(expr: str) -> str | None:
    """SWITCH with TRUE() as both value and first case never reaches later cases.

    AST-driven: a SWITCH call with at least four arguments whose value
    expression and first case are both zero-argument TRUE() calls. The
    value following the first case is the result. A TRUE() in a later
    case position stays silent.
    """
    try:
        tree = parse(expr)
    except ParseError:
        return None
    for call in _walk_calls(tree):
        if call.name.upper() != "SWITCH" or len(call.args) < 4:
            continue
        if _zero_arg_call(call.args[0], "TRUE") and _zero_arg_call(call.args[1], "TRUE"):
            return _SWITCH_CONSTANT_FIRST_CASE_MSG
    return None


_COALESCE_UNREACHABLE_MSG = (
    "COALESCE(x, BLANK(), y) never reaches y — the BLANK argument "
    "returns first when x is blank."
)


def coalesce_unreachable_after_blank(expr: str) -> str | None:
    """A BLANK() before the last COALESCE argument makes later args dead.

    AST-driven: a COALESCE call with a zero-argument BLANK() in a
    non-final position and at least one argument after it. Leading and
    trailing BLANK() forms belong to rules 61 and 39.
    """
    try:
        tree = parse(expr)
    except ParseError:
        return None
    for call in _walk_calls(tree):
        if call.name.upper() != "COALESCE" or len(call.args) < 3:
            continue
        for index in range(1, len(call.args) - 1):
            if _zero_arg_call(call.args[index], "BLANK"):
                return _COALESCE_UNREACHABLE_MSG
    return None


_REDUNDANT_DISTINCT_MSG = (
    "{outer}({inner}(x)) repeats a distinct pass — write "
    "{inner}(x)."
)


def redundant_distinct(expr: str) -> str | None:
    """DISTINCT(VALUES(col)) and VALUES(DISTINCT(col)) repeat a pass.

    AST-driven: a one-argument DISTINCT whose argument is a one-argument
    VALUES call, or the reverse. A single column is assumed, as in
    rule 19's related collapse.
    """
    try:
        tree = parse(expr)
    except ParseError:
        return None
    for call in _walk_calls(tree):
        name = call.name.upper()
        if name not in {"VALUES", "DISTINCT"} or len(call.args) != 1:
            continue
        inner = call.args[0]
        if (
            isinstance(inner, Call)
            and inner.name.upper() in {"VALUES", "DISTINCT"}
            and inner.name.upper() != name
            and len(inner.args) == 1
        ):
            return _REDUNDANT_DISTINCT_MSG.format(outer=name, inner=inner.name.upper())
    return None


_ISBLANK_CONSTANT_MSG = (
    "ISBLANK({arg}) is always {value} — the argument is a literal."
)


def isblank_constant(expr: str) -> str | None:
    """ISBLANK over a literal or BLANK() yields a compile-time constant.

    AST-driven: a one-argument ISBLANK call whose argument is a Literal
    node or a zero-argument BLANK() call. Columns and call expressions
    other than BLANK() stay silent.
    """
    try:
        tree = parse(expr)
    except ParseError:
        return None
    for call in _walk_calls(tree):
        if call.name.upper() != "ISBLANK" or len(call.args) != 1:
            continue
        arg = call.args[0]
        if isinstance(arg, Literal):
            return _ISBLANK_CONSTANT_MSG.format(arg=arg.text, value="FALSE")
        if _zero_arg_call(arg, "BLANK"):
            return _ISBLANK_CONSTANT_MSG.format(arg="BLANK()", value="TRUE")
    return None


_DUPLICATE_SWITCH_CASE_MSG = (
    "SWITCH has a repeated case value — the later branch is unreachable."
)


def duplicate_switch_case(expr: str) -> str | None:
    """A repeated case expression in SWITCH makes later branches dead.

    AST-driven: SWITCH arguments at odd indexes after the value
    expression (the case slots) are compared canonically. The default
    argument is exempt; the value expression itself is not a case.
    """
    try:
        tree = parse(expr)
    except ParseError:
        return None
    for call in _walk_calls(tree):
        if call.name.upper() != "SWITCH" or len(call.args) < 4:
            continue
        seen: set[object] = set()
        for index in range(1, len(call.args) - 1, 2):
            signature = _canonical(call.args[index])
            if signature in seen:
                return _DUPLICATE_SWITCH_CASE_MSG
            seen.add(signature)
    return None


_COUNTROWS_AT_LEAST_ONE_MSG = (
    "COUNTROWS(t) >= 1 is a non-empty test — NOT(ISEMPTY(t)) says it "
    "directly."
)


def countrows_at_least_one(expr: str) -> str | None:
    """`COUNTROWS(t) >= 1` is the same test as `COUNTROWS(t) > 0`.

    AST-driven: a COUNTROWS call compared with `>=` to the numeric
    literal 1, or `1 <= COUNTROWS(...)`. Other bounds stay rule 25's
    or no rule's territory.
    """
    try:
        tree = parse(expr)
    except ParseError:
        return None
    for binary in _walk_binaries(tree):
        left, right = binary.left, binary.right
        if binary.op == ">=" and isinstance(left, Call) and left.name.upper() == "COUNTROWS" \
                and _numeric_literal(right) == 1:
            return _COUNTROWS_AT_LEAST_ONE_MSG
        if binary.op == "<=" and _numeric_literal(left) == 1 \
                and isinstance(right, Call) and right.name.upper() == "COUNTROWS":
            return _COUNTROWS_AT_LEAST_ONE_MSG
    return None


_SINGLE_COLUMN_ITERATOR_BARE_MSG = (
    "{name}(t, [col]) reads one column per row — plain "
    "{plain}(t[col]) does the same work."
)

_PLAIN_AGGREGATE = {
    "SUMX": "SUM",
    "AVERAGEX": "AVERAGE",
    "MINX": "MIN",
    "MAXX": "MAX",
    "COUNTX": "COUNT",
    "COUNTAX": "COUNTA",
}


def single_column_iterator_bare(expr: str) -> str | None:
    """A row iterator over a bare column reference is a plain aggregate.

    AST-driven: a two-argument iterator call whose expression argument
    is a bare ColumnRef. The qualified-call form
    `SUMX('T', 'T'[col])` is rule 14's shape; an expression more
    complex than a bare column stays silent.
    """
    try:
        tree = parse(expr)
    except ParseError:
        return None
    for call in _walk_calls(tree):
        name = call.name.upper()
        if name not in _PLAIN_AGGREGATE or len(call.args) != 2:
            continue
        if isinstance(call.args[1], ColumnRef):
            return _SINGLE_COLUMN_ITERATOR_BARE_MSG.format(
                name=name, plain=_PLAIN_AGGREGATE[name]
            )
    return None


_NEGATED_MULTIPLICATION_MSG = (
    "x * -1 is -x — multiplying by negative one is scalar negation."
)


def negated_multiplication(expr: str) -> str | None:
    """`[x] * -1` is `-[x]`, BLANK included.

    AST-driven: a `*` binary with a numeric literal -1 on either side.
    BLANK propagates through multiplication, so the rewrite holds for
    every value. Division by -1 is rule 3's shape and stays silent.
    """
    try:
        tree = parse(expr)
    except ParseError:
        return None
    for binary in _walk_binaries(tree):
        if binary.op != "*":
            continue
        if _numeric_literal(binary.right) == -1 or _numeric_literal(binary.left) == -1:
            return _NEGATED_MULTIPLICATION_MSG
    return None


_SELF_CALL_COMPARISON_MSG = (
    "{op} comparing two copies of the same deterministic call gives a "
    "constant."
)

_VOLATILE = {"NOW", "TODAY", "RAND", "RANDBETWEEN", "GUID", "UTCNOW"}

_DETERMINISTIC = {
    "SUM", "MAX", "MIN", "COUNT", "COUNTA", "AVERAGE", "ABS", "ROUND",
}


def self_call_comparison(expr: str) -> str | None:
    """An `=`/`<>` binary comparing identical deterministic calls is constant.

    AST-driven: both operands are Call nodes with the same canonical
    signature and the function name is in the deterministic allowlist.
    Volatile functions (NOW, RAND, ...) are never claimed constant.
    """
    try:
        tree = parse(expr)
    except ParseError:
        return None
    for binary in _walk_binaries(tree):
        if binary.op not in {"=", "<>"}:
            continue
        left, right = binary.left, binary.right
        if not isinstance(left, Call) or not isinstance(right, Call):
            continue
        if left.name.upper() in _VOLATILE or right.name.upper() in _VOLATILE:
            continue
        if left.name.upper() in _DETERMINISTIC and _canonical(left) == _canonical(right):
            return _SELF_CALL_COMPARISON_MSG.format(op=binary.op)
    return None


_NESTED_ISBLANK_MSG = (
    "ISBLANK(ISBLANK(x)) is always FALSE — ISBLANK returns TRUE/FALSE, "
    "never BLANK."
)


def nested_isblank(expr: str) -> str | None:
    """A nested ISBLANK is a constant FALSE test.

    AST-driven: an ISBLANK call whose argument is another ISBLANK call.
    ISBLANK of a column or another function stays silent.
    """
    try:
        tree = parse(expr)
    except ParseError:
        return None
    for call in _walk_calls(tree):
        if call.name.upper() != "ISBLANK" or len(call.args) != 1:
            continue
        inner = call.args[0]
        if isinstance(inner, Call) and inner.name.upper() == "ISBLANK":
            return _NESTED_ISBLANK_MSG
    return None


_ABS_ZERO_MSG = (
    "ABS(x) = 0 is x = 0 — an absolute value is zero exactly when its "
    "argument is."
)


def abs_zero_comparison(expr: str) -> str | None:
    """`ABS(x) = 0` is `[x] = 0`; BLANK compares equal to 0 in DAX.

    AST-driven: an `=` binary with a one-argument ABS call on one side
    and the numeric literal 0 on the other. Other bounds stay silent
    (rule 15 already handles ABS against impossible negative bounds).
    """
    try:
        tree = parse(expr)
    except ParseError:
        return None
    for binary in _walk_binaries(tree):
        if binary.op != "=":
            continue
        left, right = binary.left, binary.right
        left_abs = isinstance(left, Call) and left.name.upper() == "ABS" and len(left.args) == 1
        right_abs = isinstance(right, Call) and right.name.upper() == "ABS" and len(right.args) == 1
        if left_abs and _numeric_literal(right) == 0:
            return _ABS_ZERO_MSG
        if right_abs and _numeric_literal(left) == 0:
            return _ABS_ZERO_MSG
    return None


_BLANK_IN_MINMAX_MSG = (
    "{fn}(x, BLANK()) is {result} — BLANK is ignored by MAX but is the "
    "smallest value for MIN."
)


def blank_in_minmax(expr: str) -> str | None:
    """MAX(x, BLANK()) is x; MIN(x, BLANK()) is BLANK().

    AST-driven: a two-argument MIN or MAX call with a zero-argument
    BLANK() call on either side. Other argument shapes stay silent.
    """
    try:
        tree = parse(expr)
    except ParseError:
        return None
    for call in _walk_calls(tree):
        name = call.name.upper()
        if name not in {"MIN", "MAX"} or len(call.args) != 2:
            continue
        if _zero_arg_call(call.args[0], "BLANK") or _zero_arg_call(call.args[1], "BLANK"):
            result = "[x]" if name == "MAX" else "BLANK()"
            return _BLANK_IN_MINMAX_MSG.format(fn=name, result=result)
    return None


_IF_REPEATS_CONDITION_MSG = (
    "IF(c, x, c) repeats the condition in the else branch — the test "
    "cannot change between the branches; write x."
)


def if_repeats_condition(expr: str) -> str | None:
    """An IF whose else-branch repeats its condition has a constant result.

    AST-driven: a three-argument IF whose condition and else-branch
    share a canonical subtree signature. Limited to comparisons over
    bare identifiers/columns so volatile calls are never claimed constant.
    """
    try:
        tree = parse(expr)
    except ParseError:
        return None
    bare = (ColumnRef, Ident, QualifiedColumn)
    for call in _walk_calls(tree):
        if call.name.upper() != "IF" or len(call.args) != 3:
            continue
        cond, _, no = call.args
        if not isinstance(cond, Binary) or cond.op not in {"=", "<>", "<", ">", "<=", ">="}:
            continue
        if not isinstance(cond.left, bare) or not isinstance(cond.right, (Literal, *bare)):
            continue
        if _canonical(cond) == _canonical(no):
            return _IF_REPEATS_CONDITION_MSG
    return None


_IF_ALWAYS_BLANK_MSG = (
    "IF(ISBLANK(x), x, BLANK()) returns BLANK either way — drop the IF."
)


def if_always_blank(expr: str) -> str | None:
    """`IF(ISBLANK(x), x, BLANK())` and its NOT-mirror are always BLANK.

    AST-driven: a three-argument IF where one branch is the tested
    expression and the other is a zero-argument BLANK() call, with
    ISBLANK or NOT(ISBLANK) as the condition. The tested expression must
    be a bare column/identifier for the first cut.
    """
    try:
        tree = parse(expr)
    except ParseError:
        return None
    bare = (ColumnRef, Ident, QualifiedColumn)
    for call in _walk_calls(tree):
        if call.name.upper() != "IF" or len(call.args) != 3:
            continue
        cond, yes, no = call.args
        tested: Node | None = None
        if isinstance(cond, Call) and cond.name.upper() == "ISBLANK" and len(cond.args) == 1:
            tested = cond.args[0]  # ISBLANK(x): x then BLANK()
            if not (isinstance(yes, type(tested)) and _canonical(yes) == _canonical(tested)
                    and _zero_arg_call(no, "BLANK")):
                tested = None
        if isinstance(cond, Unary) and cond.op.upper() == "NOT" \
                and isinstance(cond.operand, Call) and cond.operand.name.upper() == "ISBLANK" \
                and len(cond.operand.args) == 1:
            tested = cond.operand.args[0]  # NOT(ISBLANK(x)): BLANK() then x
            if not (_zero_arg_call(yes, "BLANK") and _canonical(no) == _canonical(tested)):
                tested = None
        if tested is not None and isinstance(tested, bare):
            return _IF_ALWAYS_BLANK_MSG
    return None


_SUMX_ADD_ZERO_MSG = (
    "SUMX(t, x + 0) is SUM(t[x]) — adding zero per row is the row loop "
    "form of a plain aggregate."
)


def sumx_add_zero(expr: str) -> str | None:
    """SUMX over `x + 0` is the same aggregate written as a row loop.

    AST-driven: a SUMX call whose second argument is a `+` binary with a
    numeric literal 0 on one side. Other iterators and expressions stay
    silent.
    """
    try:
        tree = parse(expr)
    except ParseError:
        return None
    for call in _walk_calls(tree):
        if call.name.upper() != "SUMX" or len(call.args) != 2:
            continue
        inner = call.args[1]
        if not isinstance(inner, Binary) or inner.op != "+":
            continue
        if _numeric_literal(inner.left) == 0 or _numeric_literal(inner.right) == 0:
            return _SUMX_ADD_ZERO_MSG
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
    nested_calculate,
    countrows_values,
    if_isblank_coalesce,
    summarize_extra_column,
    if_iserror_iferror,
    and_in_calculate,
    unused_variable,
    countrows_zero,
    double_negation,
    true_comparison,
    distinctcount_values,
    if_same_branches,
    sumx_constant,
    blank_not_equal,
    trim_nested,
    filter_true,
    identity_arithmetic,
    idempotent_nested,
    countx_constant,
    power_identity,
    absorbed_boolean,
    coalesce_trailing_blank,
    nested_same_predicate,
    constant_condition,
    duplicate_coalesce,
    duplicate_boolean_operand,
    indicator_sum,
    complementary_logic,
    zero_divisor,
    self_comparison,
    self_subtraction,
    trivial_var,
    duplicate_minmax,
    not_constant,
    selectedvalue_blank_default,
    if_switch,
    countrows_false_filter,
    nested_negated_predicate,
    divide_by_one,
    repeated_round,
    concatenate_two_args,
    empty_in,
    literal_condition,
    coalesce_leading_blank,
    switch_constant_first_case,
    coalesce_unreachable_after_blank,
    redundant_distinct,
    isblank_constant,
    duplicate_switch_case,
    countrows_at_least_one,
    single_column_iterator_bare,
    negated_multiplication,
    self_call_comparison,
    nested_isblank,
    abs_zero_comparison,
    blank_in_minmax,
    if_repeats_condition,
    if_always_blank,
    sumx_add_zero,
]
