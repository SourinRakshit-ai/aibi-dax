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

Exit code 0 when clean, 1 with `-` lines per finding. `--json` prints the
findings as a JSON list (`[]` when clean):

```
$ dxa lint "IF(a, 1, IF(b, 2, IF(c, 3, [D]/0)))"
- 3 nested IF calls — SWITCH(TRUE(), ...) reads better and evaluates faster.
- Raw '/' division — use DIVIDE(num, den) to absorb zero-denominator errors.
(exit 1)
```

## `dxa lint-model model.json`

Groups findings by `table.measure`; `--table T` restricts to one table.
Prints nothing and exits 0 for a clean model. Findings exit 1 with `- `
lines per finding; `--json` prints the findings map.

## `dxa parse "EXPR"`

Reduces the expression to an AST (recursive descent; exit 2 on a
genuinely unparseable sequence):

```
$ dxa parse "1 + [A]" --json
{
  "op": "+",
  "left": {
    "text": "1"
  },
  "right": {
    "name": "A"
  }
}
```

Unparseable sequences exit 2 with a `parse error:` message on stderr.
