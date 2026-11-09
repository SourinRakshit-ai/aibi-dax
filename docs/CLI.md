# CLI reference — `dxa`

## Global

```
dxa --version        # dxa 0.1.1
dxa --help
```

## `dxa metrics "EXPR"`

Prints six aligned metrics plus the composite weight:

```
$ dxa metrics "SUMX('Sales', CALCULATE([Amount]))"
tokens      9
lines       1
chars       34
functions   2
depth       2
iterators   1
weight      45
```

`--json` wraps the same payload: `{"metrics": {...}, "weight": 45}`.

## `dxa rank model.json [--top N]`

Weighs every measure in a shared-schema model dump:

```
$ dxa rank model.json --top 3
    57  Sales.Iterator Calc
    34  Sales.If Stair
    12  Sales.Clean Total
```

## `dxa lint "EXPR"`

Exit code 0 when clean, 1 with `-` lines per finding:

```
$ dxa lint "IF(a, 1, IF(b, 2, IF(c, 3, [D]/0)))"
- 3 nested IF calls — SWITCH(TRUE(), ...) reads better and evaluates faster.
- Raw '/' division — use DIVIDE(num, den) to absorb zero-denominator errors.
(exit 1)
```

## `dxa lint-model model.json`

Groups findings by `table.measure`, prints nothing and exits 0 for a clean model.
