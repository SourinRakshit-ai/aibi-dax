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

## Data-shape rules

### Raw division
`/` raises #NUM! on zero denominators; `DIVIDE(num, den[, alt])` absorbs.
AST-driven: only non-constant denominators flag — `[x] / 2` is
safe, `[x] / [Scale]` is the trap, and slashes inside string
literals never count.

### `= BLANK()` equality
Equality against BLANK is unreliable for non-numeric types; `ISBLANK(x)`
is the intended test.

## Filter-safety rules

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
