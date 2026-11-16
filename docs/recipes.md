# Cookbook

Real measures, flagged and fixed. Each recipe shows the original with
the findings it triggers, then the rewrite that silences them — with a
sentence on why the rewrite is correct. Every fence below is replayed
against the CLI by the test suite, so the output here is the output
you get.

## Data-shape: group first, compute second

The original puts a computed expression in `SUMMARIZE`'s grouping
list, where it is silently ignored — `SUMMARIZE` only groups by plain
columns:

```
$ dxa lint "SUMMARIZE('Sales', [Region], [Qty] + 1)"
- SUMMARIZE only groups by plain column references — a computed argument is silently ignored; group first with SUMMARIZE, then compute with ADDCOLUMNS.
```

The fix groups first, then computes over the grouped result:

```
$ dxa lint "ADDCOLUMNS(SUMMARIZE('Sales', [Region]), [Qty] + 1)"
no findings
```

`ADDCOLUMNS` evaluates its expression per grouped row, which is
exactly the semantics the original was reaching for.

## Filter-safety: one filter argument per conjunct

`AND(...)` in a `CALCULATE` filter is a single boolean over the
current filter context — not the two independent filters it reads as:

```
$ dxa lint "CALCULATE([Total], AND([Qty] > 0, [Price] > 100))"
- AND(...) in a CALCULATE filter is one boolean over the current context — pass each conjunct as its own filter argument; CALCULATE already ANDs them.
```

`CALCULATE` already ANDs its filter arguments, so passing them
separately states the same condition with the semantics you meant:

```
$ dxa lint "CALCULATE([Total], [Qty] > 0, [Price] > 100)"
no findings
```

Splitting is safe because each argument becomes its own filter.
`OR(...)` must *not* be split — there is no equivalent — which is why
the rule stays silent on it.

## Refactoring: dead bindings and redundant wrappers

A `VAR` that nothing reads hides the measure's real inputs:

```
$ dxa lint "VAR Margin = [Sales] - [Cost] RETURN [Sales]"
- VAR Margin is never referenced before RETURN — drop it, or use it; a dead binding hides the measure's real inputs.
```

Either use it or delete it. Using it makes the intent explicit:

```
$ dxa lint "VAR Margin = [Sales] - [Cost] RETURN Margin"
no findings
```

## Collapsing hand-rolled error handling

`IF(ISERROR(x), y, x)` is `IFERROR(x, y)` spelled out by hand — and
here the tested expression is a raw division, which raises a second
finding:

```
$ dxa lint "IF(ISERROR([Qty] / [Pack]), 0, [Qty] / [Pack])"
- Raw '/' division — use DIVIDE(num, den) to absorb zero-denominator errors.
- IF(ISERROR(x), y, x) is a hand-rolled IFERROR(x, y) — one function says it directly.
```

`DIVIDE` absorbs zero denominators itself, so one call replaces the
whole construct:

```
$ dxa lint "DIVIDE([Qty], [Pack])"
no findings
```

## Emptiness: say what you mean

Counting rows to test for emptiness works but buries the intent:

```
$ dxa lint "FILTER('Sales', COUNTROWS('Returns') = 0)"
- COUNTROWS(t) = 0 is ISEMPTY(t) — one call states the emptiness test directly (<> 0 and > 0 become NOT(ISEMPTY(t))).
```

`ISEMPTY` is the emptiness predicate:

```
$ dxa lint "FILTER('Sales', ISEMPTY('Returns'))"
no findings
```

For the non-empty case (`<> 0` or `> 0`) wrap it: `NOT(ISEMPTY(...))`.

## Where to go next

- [Anti-pattern rules](rules.md) — every rule, why it fires, and its
  AST-driven exemptions.
- [Performance](performance.md) — what the weight measures and where
  the cost actually goes.
- [CLI reference](CLI.md) — flags, JSON shapes, and exit codes.
