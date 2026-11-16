# DAX anti-patterns — the reference

Each rule shipped by `dxa lint` with its reasoning and a fix. Community
DAX guidance (SQLBI, DAX Guide) is the common source of truth; the engine
here flags the pattern and the message names the preferred form.

## Context rules

### CALCULATE inside an iterator
`SUMX('Sales', CALCULATE([Amount]))` — the iterator's row context shadows
the filter context CALCULATE would use, so the result rarely matches
intent. Hoist CALCULATE outside or pass explicit filters.

### EARLIER(...)
Deprecated since `VAR` became the idiomatic way to capture an outer row.
Capture once, reference by name — it type-checks and stays readable.

### ALL / FILTER(ALL(...)) as an aggregate's first argument
`SUMX(ALL('Sales'), ...)` walks every row through the filter machinery.
A boolean filter (`'Sales'[Col] = value`) inside `CALCULATE` prunes the
table during scan instead of after.

### FILTER inside an aggregate
`COUNTROWS(FILTER('Sales', cond))` and `SUMX(FILTER('Sales', cond), …)`
build a filtered table in memory before aggregating. The same condition
as a `CALCULATE` filter is pushed into the scan:
`CALCULATE(COUNTROWS('Sales'), cond)`. Only the aggregate's **first**
argument is checked, so `FILTER` used elsewhere — a `CALCULATE` filter
argument, a nested step — stays silent.

### Nested `CALCULATE`
`CALCULATE(CALCULATE(x, f1), f2)` — the inner context transition is a
no-op, because the outer call has already transitioned before it
evaluates its first argument. Merge the filter lists instead:
`CALCULATE(x, f1, f2)`. Only direct nesting flags: a `CALCULATE` deeper
in the expression either sits behind a row iterator (rule 1's real
context work) or is an ordinary conditional.

## Refactoring rules

### Three or more IF calls
`SWITCH(TRUE(), cond, value, ...)` states a decision table rather than a
staircase, and evaluates each branch once.

### IFERROR overreach
`IFERROR(expr, blank)` turns *any* failure into silence — including bugs.
Prefer `DIVIDE`'s third argument, or fix what raises.

### HASONEVALUE + VALUES pairs
`IF(HASONEVALUE(k), VALUES(k), other)` is exactly `SELECTEDVALUE(k, other)`.

### SWITCH without a default
`SWITCH(expr, v1, r1, v2, r2)` returns BLANK when nothing matches — silently.
The optional final argument states the miss case explicitly, even if it is
`0` or an error message. The rule counts arguments on the AST: an even
number after the first means no default is present.

### Single-column row iterator
`SUMX('Sales', 'Sales'[Amount])` walks the table to read one column; the
plain aggregate `SUM('Sales'[Amount])` is faster and identical. The rule
matches the iterator's first argument against the column's table
qualification on the AST, so mismatched tables stay flagged as real
iteration.

### `COUNTROWS(VALUES(...))`
`COUNTROWS(VALUES('Sales'[Region]))` builds the distinct table only to
count its rows; `DISTINCTCOUNT('Sales'[Region])` says the intent outright
with no intermediate materialization. Same for `COUNTROWS(DISTINCT(col))`.
Only a single-column `VALUES`/`DISTINCT` flags — `COUNTROWS(VALUES('Sales'))`
counts rows of the whole table and has no `DISTINCTCOUNT` one-liner.

### ABS against an impossible bound
`ABS(x)` is never negative, so `ABS(x) < 0` (and `<= n` for negative n,
mirrored as `0 > ABS(x)` / `-1 >= ABS(x)`) can never hold — almost always
a sign slip. AST-driven: one side is a one-argument ABS call, the other a
numeric literal; the always-true mirrors (`ABS(x) >= 0`) are legitimate
defensive style and stay silent.

### IF with TRUE()/FALSE() branches
`IF(cond, TRUE(), FALSE())` computes the value the condition already is —
one branch and a boolean coercion for nothing. Write `cond`; for the
inverted `IF(cond, FALSE(), TRUE())` write `NOT cond`. AST-driven: only a
three-argument IF whose last two arguments are zero-argument `TRUE()` /
`FALSE()` calls flags, so bare `TRUE` identifiers and two-argument IFs
stay silent.

### A `VAR` never referenced before `RETURN`
`VAR a = 1 RETURN 2` defines a binding the measure never reads — dead
variables hide a measure's real inputs and suggest a half-finished
refactor. AST-driven: walk the `VAR` left spine and search every later
value plus the `RETURN` body for a matching bare identifier
(case-insensitive). A variable read by a later `VAR` counts as used
(`VAR a = 1 VAR b = a + 1 RETURN b` is clean); the first dead binding
reports, naming the variable.

## Data-shape rules

### Raw division
`/` raises #NUM! on zero denominators; `DIVIDE(num, den[, alt])` absorbs.
AST-driven: only non-constant denominators flag — `[x] / 2` is
safe, `[x] / [Scale]` is the trap, and slashes inside string
literals never count.

### `= BLANK()` equality
Equality against BLANK is unreliable for non-numeric types; `ISBLANK(x)`
is the intended test.

### `IF(ISBLANK(x), y, x)`
`IF(ISBLANK([Amount]), 0, [Amount])` restates the tested expression in
its own else-branch — `COALESCE([Amount], 0)` says it once and reads as
"first non-blank wins". AST-driven: only a three-argument IF whose
condition is a one-argument `ISBLANK` **and** whose else-branch equals
the tested expression flags; `IF(ISBLANK([A]), 0, [B])` is a genuine
conditional and stays silent.

### `SUMMARIZE` with a computed argument
`SUMMARIZE('Sales', [Region], [Qty] + 1)` puts a computed expression in
the grouping list, where it is silently ignored — `SUMMARIZE` only
groups by plain columns. Group first (`SUMMARIZE('Sales', [Region])`),
then compute over the result with `ADDCOLUMNS`. AST-driven: only a
plain `[Col]` or `'T'[Col]` argument after the table passes;
`ADDCOLUMNS(SUMMARIZE(...), …)` — the correct pattern — never flags.

### `IF(ISERROR(x), y, x)`
`IF(ISERROR([Amount]), BLANK(), [Amount])` is a hand-spelled
`IFERROR([Amount], BLANK())` — the long form only hides the intent.
AST-driven: only a three-argument IF whose condition is a
one-argument `ISERROR` **and** whose else-branch equals the tested
expression flags; `IF(ISERROR([A]), 0, [B])` is a genuine
conditional and stays silent. Distinct from the `IFERROR` overreach
rule, which flags *using* IFERROR too liberally.

### `COUNTROWS(t) = 0`
`IF(COUNTROWS('Sales') = 0, …)` states "this table has no rows" in
the long form; `ISEMPTY('Sales')` says it in one call. AST-driven: a
`COUNTROWS(` call compared against the numeric literal 0 with `=`,
`<>`, or `>` flags (`<> 0` and `> 0` become `NOT(ISEMPTY(t))`;
either operand order for `=`). Comparisons against other values, and
impossible tests like `COUNTROWS(t) < 0`, stay silent.

### `NOT(NOT(x))`
Double negation cancels — `NOT(NOT(cond))` is `cond`. The wrapped
form reads as if some transformation happened when none did, and
usually means a refactor left a redundant wrapper behind. AST-driven:
`NOT` parses as a prefix operator, so a `NOT`/`!` whose operand is
another `NOT`/`!` flags (mixed spellings like `NOT(!x)` cancel too);
`NOT(NOT(NOT(x)))` reports once. Arithmetic `-(-x)` and single
negations stay silent.

## Filter-safety rules

### `AND(...)` as a `CALCULATE` filter
`CALCULATE([m], AND([A] > 0, [B] < 10))` passes one boolean over the
current filter context instead of two independent filters — pass each
conjunct as its own argument (`CALCULATE([m], [A] > 0, [B] < 10)`);
`CALCULATE` already ANDs its filter arguments together. AST-driven:
an `AND(` call or a `&&` binary among the filter arguments of
`CALCULATE`/`CALCULATETABLE` flags. `OR(` and `||` stay silent —
splitting them would change semantics.

### Bare ALL(table)
As a filter eraser `REMOVEFILTERS(table)` says exactly that; keep ALL
where you need its modifying semantics.

### `&` inside CONCATENATEX
Concatenate via the iterator's arguments; mixing `&` inside is ordering
hazard with hidden separators. AST-driven: `&` inside a string
literal is data and never flags.

## Style

### Lowercase function calls
DAX function names are uppercase by convention — `sum(` is a typo until
proven otherwise. Literal strings and bracketed columns are exempt.

### Nested row iterators
`SUMX('Sales', AVERAGEX('Sales', [x]))` pays a context transition per row
for every iterator on the path. Capture the outer step in a `VAR` and
aggregate over it. This rule runs over the parser AST — the tree is why it
knows how deep the iterators stack.
