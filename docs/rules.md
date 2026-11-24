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

### `DISTINCTCOUNT(VALUES(col))`
`DISTINCTCOUNT(VALUES('Sales'[Region]))` runs a distinct pass and then
counts the distinct set — `DISTINCTCOUNT('Sales'[Region])` returns the
same number in one call. AST-driven: a single-argument `DISTINCTCOUNT`
whose argument is a single-column `VALUES`/`DISTINCT` call flags;
table-valued arguments and everything else stays silent.

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

### `IF(cond, x, x)`
`IF([cond], [x] * 2, [x] * 2)` returns the same value whichever way the
condition resolves — the condition computes for nothing. AST-driven: the
last two arguments of a three-argument `IF` are compared with a canonical
subtree signature (DAX identifiers case-insensitive, numbers by value,
strings case-sensitive); any shared shape flags (`if_same_branches`).

### `c && c`, `c || c`, `AND(c, c)`, `OR(c, c)`
Two copies of the same truth value produce nothing new — the boolean
operator is idempotent on that pair (`duplicate_boolean_operand`).
AST-driven: an `AND(`/`OR(` call or `&&`/`||` binary whose arguments
share a canonical subtree signature (identifiers fold case, numbers
compare by value) flags. Absorption by `TRUE()`/`FALSE()` stays rule
38's territory; non-equal operands stay silent.

### `IF(TRUE(), x, y)` / `IF(FALSE(), x, y)`
`IF(TRUE(), [Revenue], [Cost])` always returns the first branch, and
`IF(FALSE(), [Revenue], [Cost])` always returns the second — the
unreachable branch is dead code and the `TRUE()`/`FALSE()` condition
is leftover generator output (`constant_condition`). AST-driven: a
three-argument IF whose condition is a zero-argument `TRUE()` or
`FALSE()` call flags with the live branch named; non-constant
conditions stay silent.

### `COALESCE(x, …, x)`
`COALESCE([x], [x], [y])` — a duplicate argument in a later position
never runs; the first non-blank wins before control reaches the copy
(`duplicate_coalesce`). AST-driven: arguments are compared with the
canonical subtree signature (identifiers fold case, numbers compare
by value); any repeat flags. Single-argument calls and unparseable
text stay silent.

### `NAME(NAME(x))` idempotents
`UPPER`, `LOWER`, `ABS` and `INT` are exact idempotents — the nested
call adds a function hop and nothing else. AST-driven: a single-argument
call whose argument is the same function flags, and the message names the
function (`idempotent_nested`); `TRIM(TRIM(x))` has its own rule.

### `POWER(x, 1)` / `POWER(x, 0)`
`POWER([x], 1)` returns the base, `POWER([x], 0)` returns 1 — the
exponent rules give you exactly that, and the linter also parses the
`^` caret operator (right-associative, binds tighter than unary), so
`[x] ^ 1` and `[x] ^ 0` flag the same way (`power_identity`). The
first-argument-only rule still holds: bare `POWER(` and `^` share one
implementation; `POWER(x, 2)`, `x ^ 2` and non-literal exponents stay
silent.

### `SUMX(t, k)` with a constant
`SUMX('Sales', 1)` adds up the same number once per row —
`COUNTROWS('Sales')` (or `COUNTROWS(t) * k`) is the value with no row
loop (`sumx_constant`). Only SUMX-level: on an empty table `SUMX`
returns 0, which equals `COUNTROWS * k`, while `AVERAGEX`/`MAXX`
return BLANK — suggesting one call for those would be wrong advice.

### `COUNTX(t, k)` with a constant
`COUNTX('Sales', 1)` walks every row to tally the same constant —
`COUNTROWS('Sales')` is the value without the loop (same for
`COUNTAX`; `countx_constant`). AST-driven: a numeric literal (possibly
negated) on the second argument flags; a constant is never blank, so
every row counts exactly — the count sibling of the `SUMX(t, k)` rule.

### `TRIM(TRIM(x))`
`TRIM` is idempotent — the nested pair changes nothing the outer call
cannot (`trim_nested`). AST-driven: a `TRIM(` call whose only argument
is another `TRIM(` call flags; mixed wrappers like
`TRIM(LOWER(TRIM(x)))` stay silent.

### `SUMX(t, IF(c, 1, 0))`
`SUMX('Sales', IF([Qty] > 0, 1, 0))` walks the table and adds a 1
per passing row — `COUNTROWS(FILTER('Sales', [Qty] > 0))` is the
same value with no loop (`indicator_sum`). AST-driven: a `SUMX(`
call whose second argument is a three-argument `IF` whose last two
arguments are exactly the numeric literals 1 and 0 (strings `"1"`/`"0"`
don't count); the inverted `IF(c, 0, 1)` reads as "failing rows" and
stays silent.

### `DIVIDE(x, 0)`
Dividing by a literal zero never varies the result: the call returns BLANK
(or its alternate argument) whatever the numerator is (`zero_divisor`).
AST-driven: a two-or-more-argument `DIVIDE(` whose second argument is a
numeric literal zero. A column denominator and other numeric literals
stay silent.

### `[x] = [x]` / `[x] <> [x]`
Comparing a bare column or identifier with itself gives a constant: TRUE
or FALSE respectively (`self_comparison`). BLANK compares equal to itself
in DAX, so the collapse holds for every value. Only bare references are
considered; call expressions are left alone.

### `x - x`
Subtracting a value from itself is 0; BLANK converts to 0 in subtraction,
so the result is the same for blank inputs (`self_subtraction`). Only
bare references are flagged; call expressions are not claimed constant.

### `VAR a = value RETURN a`
A variable whose only use is the RETURN statement adds a name and nothing
else (`trivial_var`): writing the value directly is exact because both
forms evaluate it in the same row context. Case-insensitive matching a
different identifier (`RETURN total` for `VAR Total`) also flags. A
variable read by a later VAR or used inside a larger expression stays
silent.

### `MIN(x, x)` / `MAX(x, x)`
Two copies of the same argument produce that argument, blank included
(`duplicate_minmax`). AST-driven: a two-argument MIN or MAX call with a
canonical-signature match between the arguments; differing arguments
and other arities stay silent.

### `NOT(TRUE())` / `NOT(FALSE())` / `NOT(BLANK())`
NOT over a constant is itself a constant (`not_constant`): FALSE for
TRUE(), TRUE for FALSE() and BLANK(). A BLANK operand behaves as FALSE
in a boolean context, so the fold is exact. NOT over a column or any
other expression stays silent.

### `SELECTEDVALUE(t[c], BLANK())`
BLANK() is the value SELECTEDVALUE returns on its own when there is no
single visible value, so the explicit alternate changes nothing
(`selectedvalue_blank_default`). Only a two-argument call with a
zero-argument BLANK() fallback flags; a real fallback such as 0 stays
silent.

### `IF(x = k1, a, IF(x = k2, b, c))`
Two nested IFs comparing the same bare column against different literals
are a lookup, and `SWITCH(x, k1, a, k2, b, c)` expresses it once
(`if_switch`). Deeper chains report once. Different tested columns,
comparison operators other than `=`, and duplicate case literals stay
silent.

### `IF(c, IF(NOT(c), a, b), d)`
The inner condition is decided by the outer branch: when `c` is true the
negation is false, so the inner IF returns `b` (`nested_negated_predicate`).
The mirrored shape with the nested IF in the else branch reduces to
`IF(c, d, a)`. BLANK takes the false branch in both cases.

### `DIVIDE(x, 1)`
A denominator of 1 returns the numerator unchanged, and BLANK divided by
1 is BLANK (`divide_by_one`). The alternate-result form is likewise
equivalent because the alternate is unreachable. Numeric literals other
than 1 and column denominators stay silent.

### `ROUND(ROUND(x, n), n)`
Rounding twice to the same precision is the same as rounding once
(`repeated_round`). AST-driven: a two-argument ROUND whose inner ROUND
uses the same digits argument under the canonical signature. Different
precisions and ROUNDUP/ROUNDDOWN stay silent.

### `CONCATENATE(a, b)`
With exactly two arguments, CONCATENATE is the `&` operator written out
(`concatenate_two_args`): both coerce their operands to text the same way,
including BLANK. Calls with a different arity stay silent.

### `x IN {}`
Membership in an empty list never succeeds, so the expression is FALSE
for every value, BLANK included (`empty_in`). AST-driven: an IN binary
with an empty List on the right. Non-empty lists and other right-hand
shapes stay silent.

### `IF(1 = 1, x, y)`
Comparing two numeric literals gives a compile-time constant, so the IF
always returns the same branch (`literal_condition`). The six comparison
operators are covered; conditions involving a column, a call or a
non-comparison operator stay silent.

### `COALESCE(BLANK(), x)`
COALESCE returns its first non-BLANK argument, so a leading BLANK() is
always skipped (`coalesce_leading_blank`). The rule flags the leading
position only; trailing BLANK() and one-argument forms belong to rule 39.

### `COALESCE(x, BLANK(), y)`
A zero-argument BLANK() in a non-final position is returned as soon as
the earlier arguments are blank, so every later argument is unreachable
(`coalesce_unreachable_after_blank`). Leading and trailing BLANK()
arguments are covered by rules 61 and 39.

### `DISTINCT(VALUES(col))` / `VALUES(DISTINCT(col))`
Both functions return the distinct values of a column, so nesting one in
the other repeats a pass (`redundant_distinct`). Only one-argument forms
with the two names alternating are flagged; a single call and
same-name nesting stay silent.

### `ISBLANK(1)` / `ISBLANK(BLANK())`
A literal is never blank, and BLANK() always is, so these calls are
constants (`isblank_constant`). A literal argument suggests FALSE; a
zero-argument BLANK() suggests TRUE. Tests over columns or other calls
stay silent.

### `SWITCH(x, k, a, k, b, c)`
A repeated case expression can never be reached: SWITCH takes the first
matching case (`duplicate_switch_case`). Case slots are compared with
the canonical signature; the trailing default argument is exempt.

### `COUNTROWS(t) >= 1`
COUNTROWS returns a non-negative integer, so `>= 1` is exactly the
non-empty test (`countrows_at_least_one`). `NOT(ISEMPTY(t))` says the
same thing. Both operand orders flag; other bounds stay silent.

### `x * -1`
Multiplying by negative one is negation written the long way
(`negated_multiplication`): BLANK propagates through multiplication, so
`BLANK() * -1` and `-BLANK()` agree. Either operand position flags;
other multipliers and division by -1 stay silent.

### `SUM(x) = SUM(x)`
Comparing two copies of the same deterministic call is a constant, just
as comparing a bare column to itself is (`self_call_comparison`). Only
an allowlist of deterministic functions qualifies; volatile functions
like NOW() and RAND() are never claimed constant.

### `ISBLANK(ISBLANK(x))`
ISBLANK returns TRUE or FALSE, never BLANK, so wrapping it in another
ISBLANK is always FALSE (`nested_isblank`). A single guard over a column
or another function stays silent.

### `ABS(x) = 0`
An absolute value is zero exactly when its argument is zero, and BLANK
compares equal to 0 in DAX, so both forms agree on blanks
(`abs_zero_comparison`). Either operand order flags; inequality and
other bounds stay silent.

### `SUMX(t, [col])` with a bare column
A row iterator whose expression is a bare column reference pays for row
context to do what a plain aggregate does (`single_column_iterator_bare`).
Six iterator families are covered. The qualified form `SUMX('T', 'T'[col])`
stays rule 14's territory.

### `SWITCH(TRUE(), TRUE(), x, ...)`
When the value expression and the first case are both TRUE(), that case
always matches and later cases are unreachable
(`switch_constant_first_case`). Only the first case position flags; a
TRUE() in a later case is legitimate.

### `COUNTROWS(FILTER(t, FALSE()))`
A FALSE() predicate leaves no rows, so the count is the literal 0
(`countrows_false_filter`). AST-driven: COUNTROWS of a FILTER whose
condition is a zero-argument FALSE() call. TRUE() filters and real
conditions stay silent.

### `x || NOT(x)` / `x && NOT(x)`
Complementary operands make the outcome independent of `x`
(`complementary_logic`): OR with a negation is always TRUE, AND is
always FALSE. BLANK follows the same boolean coercion, so the collapse
holds for every value. AST-driven: one operand is a NOT/! unary over
the other under the canonical signature; `OR(a, NOT(b))` stays silent.

### `OR(TRUE(), x)` / `AND(FALSE(), x)`
A constant absorbs every other operand: `OR(TRUE(), [x])` is `TRUE()`,
`AND(FALSE(), [x])` is `FALSE()` — the rest of the expression is dead
weight (`absorbed_boolean`). AST-driven: a zero-argument `TRUE()`
anywhere in an `OR(` call or a `||` binary, or a zero-argument
`FALSE()` anywhere in an `AND(` call or a `&&` binary, flags. The
identity pair — `OR(FALSE(), x)` and `AND(TRUE(), x)` — is not flagged.

### A `VAR` never referenced before `RETURN`
`VAR a = 1 RETURN 2` defines a binding the measure never reads — dead
variables hide a measure's real inputs and suggest a half-finished
refactor. AST-driven: walk the `VAR` left spine and search every later
value plus the `RETURN` body for a matching bare identifier
(case-insensitive). A variable read by a later `VAR` counts as used
(`VAR a = 1 VAR b = a + 1 RETURN b` is clean); the first dead binding
reports, naming the variable.

### Identity arithmetic
`[x] * 1`, `1 * [x]` and `[x] / 1` return exactly the other operand —
BLANKs propagate in multiplication and division, so these hold for
every value (`identity_arithmetic`). AST-driven: a binary `*` or `/`
with the numeric literal 1 on the identity side flags; `1 / x` is a
reciprocal, `0 * x` is absorbing, and `[x] + 0` is NOT an identity —
BLANK converts to 0 in sums and subtractions, so additive zero is the
documented idiom to display blank measures as zeros and stays silent.

## Data-shape rules

### Raw division
`/` raises #NUM! on zero denominators; `DIVIDE(num, den[, alt])` absorbs.
AST-driven: only non-constant denominators flag — `[x] / 2` is
safe, `[x] / [Scale]` is the trap, and slashes inside string
literals never count.

### `[x] <> BLANK()`
The not-equal twin of the `= BLANK()` habit — `NOT(ISBLANK([x]))` states
the test outright. AST-driven: a `<>` binary with a zero-argument
`BLANK()` call on either side flags; `= BLANK()` stays the other rule's
territory, as do other operators and unparseable text.

### `= BLANK()` equality
Equality against BLANK is unreliable for non-numeric types; `ISBLANK(x)`
is the intended test.

### `IF(ISBLANK(x), y, x)`
`IF(ISBLANK([Amount]), 0, [Amount])` restates the tested expression in
its own else-branch — `COALESCE([Amount], 0)` says it once and reads as
"first non-blank wins". The special case `IF(ISBLANK([Amount]), BLANK(),
[Amount])` goes straight to `COALESCE(t, BLANK())`, which is `t` — the
message says write the expression directly (no COALESCE detour). The
negated twin `IF(NOT(ISBLANK(t)), t, BLANK())` is the same collapse
written upside-down — it also collapses to `t` and flags with the same
"write the tested expression" message. AST-driven: only a
three-argument IF whose condition is a one-argument `ISBLANK` (or a
`NOT`/`!`-wrapped one) **and** whose matching branch equals the
tested expression flags; `IF(ISBLANK([A]), 0, [B])` is a genuine
conditional and stays silent.

### `IF(c, … IF(c, …) …)`
When the outer branch is reached, the condition is already decided —
`IF([c], IF([c], 1, 2), 3)` reduces to `IF([c], 1, 3)`, and the else
branch symmetric: `IF([c], 3, IF([c], 1, 2))` reduces to `IF([c], 3, 2)`.
AST-driven: a three-argument IF whose second or third argument is
another three-argument IF with a canonically equal predicate (idents
fold case, numbers compare by value) flags; deeper nesting and
unparseable text stay silent.

### `COALESCE(..., BLANK())` / `COALESCE(x)`
`COALESCE([x], BLANK())` says the same thing as `COALESCE([x])` — the
trailing alternative is the default anyway. And a single-argument
`COALESCE([x])` is exactly `[x]`. AST-driven: a zero-argument
`BLANK()` in the LAST argument flags (a middle `BLANK()` short-
circuits to blank and hides later arguments from evaluation — it
changes what runs, not just what's returned, so it stays silent), as
does a one-argument call; unparseable text stays silent.

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

### `[flag] = TRUE()`
`FILTER('Sales', [Active] = TRUE())` compares a boolean against
`TRUE()` when the column already *is* the boolean — the comparison
adds a coercion and a word that carries no information. Write
`[Active]`; `[Active] = FALSE()` becomes `NOT [Active]`. AST-driven:
an `=`/`<>` binary with a zero-argument `TRUE()`/`FALSE()` call on
either side flags; `TRUE()` in an IF branch (the `IF(cond, TRUE(),
FALSE())` rule's territory) and bare `TRUE` identifiers stay silent.

## Filter-safety rules

### `AND(...)` as a `CALCULATE` filter
`CALCULATE([m], AND([A] > 0, [B] < 10))` passes one boolean over the
current filter context instead of two independent filters — pass each
conjunct as its own argument (`CALCULATE([m], [A] > 0, [B] < 10)`);
`CALCULATE` already ANDs its filter arguments together. AST-driven:
an `AND(` call or a `&&` binary among the filter arguments of
`CALCULATE`/`CALCULATETABLE` flags. `OR(` and `||` stay silent —
splitting them would change semantics.

### `FILTER(t, TRUE())`
`FILTER('Sales', TRUE())` passes every row, so it returns every row —
write the table instead of the iterator (`filter_true`). AST-driven:
a `FILTER(` call whose second argument is a zero-argument `TRUE()`
flags; `FALSE()` (no empty-table literal) and bare `TRUE` identifiers
stay silent.

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

## Rule index

Machine-checked by the test suite: every rule in the linter appears here.

- `calculate_inside_iterator` — CALCULATE inside a row-iterator: filter context is overridden per-row by the iterator, so the result is usually wrong or misleading
- `too_many_ifs` — Three or more IF( call sites: SWITCH(TRUE(), ...) is flatter
- `raw_division` — / without DIVIDE( raises #NUM! on zero denominators
- `blank_comparison` — `= BLANK()` misses semantics; ISBLANK expresses intent
- `bare_all_table` — Single-argument ALL(table) used as a filter eraser — REMOVEFILTERS is unambiguous
- `concat_ampersand` — String concatenation '&' inside CONCATENATEX is redundant
- `earlier_var` — EARLIER is superseded by VAR capture — flat and type-checkable.
- `all_first_argument` — An iterator or CALCULATE aggregating directly over ALL / FILTER(ALL(...)) walks every row through the filter machinery; a boolean filter in CALCULATE prunes earlier and reads better.
- `iferror_overuse` — IFERROR masks model bugs behind silent blanks — an explicit error contract (or DIVIDE's third argument) says what you mean
- `values_with_hasonevalue` — HASONEVALUE + VALUES is the long-form SELECTEDVALUE.
- `lowercase_function` — DAX has no lowercase callable identifiers, so a bare lowercase word before ( is almost always a mistyped function name
- `nested_iterators` — An iterator inside another iterator pays a context transition per row — usually a VAR capture of the outer step computes the same result for a fraction of the effort
- `switch_missing_default` — A SWITCH whose argument list holds only value/result pairs falls through to BLANK when nothing matches; the optional final argument makes the miss explicit
- `single_column_iterator` — `SUMX('Sales', 'Sales'[Amount])` is a plain aggregate in disguise
- `abs_negative_comparison` — `ABS(x) < 0` and friends can never hold: ABS returns a non-negative
- `if_true_false_branches` — `IF(cond, TRUE(), FALSE())` is `cond`; the branch is pure waste
- `filter_inside_aggregate` — `COUNTROWS(FILTER(…))` / `SUMX(FILTER(…), …)` materialize a table
- `nested_calculate` — `CALCULATE(CALCULATE(...))`: the inner transition is redundant
- `countrows_values` — `COUNTROWS(VALUES('T'[Col]))` collapses to `DISTINCTCOUNT('T'[Col])`
- `if_isblank_coalesce` — `IF(ISBLANK(x), y, x)` collapses to `COALESCE(x, y)`
- `summarize_extra_column` — `SUMMARIZE('T', [A], [B] + 1)` drops the computed argument
- `if_iserror_iferror` — `IF(ISERROR(x), y, x)` collapses to `IFERROR(x, y)`
- `and_in_calculate` — `CALCULATE(m, AND(a, b))` should be `CALCULATE(m, a, b)`
- `unused_variable` — A `VAR` never referenced before `RETURN` is a dead binding
- `countrows_zero` — `COUNTROWS(t) = 0` is `ISEMPTY(t)`
- `double_negation` — `NOT(NOT(x))` collapses to `x`
- `true_comparison` — `[flag] = TRUE()` is `[flag]`; `[flag] = FALSE()` is `NOT [flag]`
- `distinctcount_values` — `DISTINCTCOUNT(VALUES('T'[Col]))` collapses to `DISTINCTCOUNT('T'[Col])`
- `if_same_branches` — `IF(cond, x, x)` is `x` — the predicate computes for nothing
- `sumx_constant` — `SUMX(t, k)` with a numeric literal k is `COUNTROWS(t) * k`
- `blank_not_equal` — `[x] <> BLANK()` is `NOT(ISBLANK([x]))`
- `trim_nested` — `TRIM(TRIM(x))` collapses to `TRIM(x)`
- `filter_true` — `FILTER(t, TRUE())` is `t`
- `identity_arithmetic` — `x * 1`, `1 * x` and `x / 1` return x — even for blanks
- `idempotent_nested` — `UPPER(UPPER(x))` is `UPPER(x)` — same for LOWER, ABS, INT
- `countx_constant` — `COUNTX(t, k)` (or `COUNTAX(t, k)`) with numeric literal k is `COUNTROWS(t)`
- `power_identity` — `POWER(x, 1)` and `x ^ 1` are `x`; the zero-exponent twins are `1`
- `absorbed_boolean` — `OR(TRUE(), x)` is `TRUE()`; `AND(FALSE(), x)` is `FALSE()`
- `coalesce_trailing_blank` — `COALESCE(..., BLANK())` drops the trailing default; `COALESCE(x)` is `x`
- `nested_same_predicate` — `IF(c, IF(c, a, b), d)` is `IF(c, a, d)`; same for the else branch
- `constant_condition` — `IF(TRUE(), x, y)` is `x`; `IF(FALSE(), x, y)` is `y`
- `duplicate_coalesce` — `COALESCE(x, …, x)` — a repeated later argument is unreachable
- `duplicate_boolean_operand` — `c && c` is `c`; same for `||`, `AND(c, c)` and `OR(c, c)`
- `indicator_sum` — `SUMX(t, IF(c, 1, 0))` is `COUNTROWS(FILTER(t, c))`
- `complementary_logic` — `x || NOT(x)` is TRUE; `x && NOT(x)` is FALSE
- `zero_divisor` — `DIVIDE(x, 0)` has no real division to perform
- `self_comparison` — `[x] = [x]` is TRUE; `[x] <> [x]` is FALSE
- `self_subtraction` — `[x] - [x]` is 0, including for blanks (BLANK converts to 0)
- `trivial_var` — `VAR a = value RETURN a` is `value`
- `duplicate_minmax` — `MIN(x, x)` and `MAX(x, x)` are `x`, including for blanks
- `not_constant` — NOT over a zero-argument logical constant folds to a constant
- `selectedvalue_blank_default` — A BLANK() fallback to SELECTEDVALUE is its existing default
- `if_switch` — Nested equality IFs on the same column form a SWITCH lookup
- `countrows_false_filter` — Counting a FALSE-filtered table always yields the literal 0
- `nested_negated_predicate` — A branch-nested IF whose predicate is NOT of the outer one collapses
- `divide_by_one` — `DIVIDE(x, 1)` is `x`, BLANK included
- `repeated_round` — ROUND(ROUND(x, n), n) is ROUND(x, n)
- `concatenate_two_args` — Two-argument CONCATENATE is `&` with the same operands
- `empty_in` — `[x] IN {}` is FALSE for every value, BLANK included
- `literal_condition` — An IF whose condition compares two numeric literals is constant
- `coalesce_leading_blank` — A leading BLANK() in COALESCE is always skipped
- `switch_constant_first_case` — SWITCH with TRUE() as both value and first case never reaches later cases
- `coalesce_unreachable_after_blank` — A BLANK() before the last COALESCE argument makes later args dead
- `redundant_distinct` — DISTINCT(VALUES(col)) and VALUES(DISTINCT(col)) repeat a pass
- `isblank_constant` — ISBLANK over a literal or BLANK() yields a compile-time constant
- `duplicate_switch_case` — A repeated case expression in SWITCH makes later branches dead
- `countrows_at_least_one` — `COUNTROWS(t) >= 1` is the same test as `COUNTROWS(t) > 0`
- `single_column_iterator_bare` — A row iterator over a bare column reference is a plain aggregate
- `negated_multiplication` — `[x] * -1` is `-[x]`, BLANK included
- `self_call_comparison` — An `=`/`<>` binary comparing identical deterministic calls is constant
- `nested_isblank` — A nested ISBLANK is a constant FALSE test
- `abs_zero_comparison` — `ABS(x) = 0` is `[x] = 0`; BLANK compares equal to 0 in DAX
