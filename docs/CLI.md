# CLI reference — `dxa`

## Global

```
dxa --version        # dxa 0.2.1
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

Anti-pattern findings for one expression. Exit code 0 when clean, 1 with
`-` lines per finding. `--json` prints the findings as a JSON list (`[]`
when clean). `--rule NAME` runs a single rule (function name, exit 2 with
the rule list on stderr if unknown). `--list-rules` prints the rule
inventory with each rule's summary and exits 0:

```
$ dxa lint "IF(a, 1, IF(b, 2, IF(c, 3, [D]/[E])))"
- 3 nested IF calls — SWITCH(TRUE(), ...) reads better and evaluates faster.
- Raw '/' division — use DIVIDE(num, den) to absorb zero-denominator errors.
(exit 1)
```

## `dxa explain RULE`

Full documentation for one rule — its docstring, underlined. Exit 2 with
the complete rule list on stderr if the name is unknown:

```
$ dxa explain earlier_var
earlier_var
-----------
EARLIER is superseded by VAR capture — flat and type-checkable.
```

## `dxa lint-model model.json`

Groups findings by `table.measure`; `--table T` restricts to one table.
`--rule NAME` runs a single rule (function name, exit 2 with the rule list
on stderr if unknown). Prints nothing and exits 0 for a clean model.
Findings exit 1 with `- ` lines per finding; `--json` prints the findings
map.

## `dxa parse "EXPR"`

Reduces the expression to an AST (recursive descent; exit 2 on a
genuinely unparseable sequence). `--json` prints the tree as JSON;
`--tree` prints it one node per line, children indented, with `field:`
labels where position alone would not say what the child is:

```
$ dxa parse "1 + [A]" --tree
Binary op='+'
  left:
    Literal text='1'
  right:
    ColumnRef name='A'
```

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

The grammar covers `VAR … RETURN` blocks, calls, qualified columns,
list literals, and the operator ladder `||`, `&&`, comparison/`IN`,
`+ -`, `&`, `* /`, unary. `IN` binds with the comparisons, and its
right side is usually a list. Table qualifiers may be quoted or bare
(`'Sales'[Amount]`, `Sales[Amount]`):

```
$ dxa parse "[k] IN {1, 2}" --tree
Binary op='IN'
  left:
    ColumnRef name='k'
  right:
    List
      Literal text='1'
      Literal text='2'
```
