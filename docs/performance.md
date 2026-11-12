# Performance

The linter is designed for interactive use: `dxa lint-model` runs in
milliseconds over realistic dumps, so nothing here needs caching,
threading, or a server. This page records what each stage costs and how
the numbers are produced.

## Corpus

`examples/bench_rules.py` defines a 22-expression corpus covering every
rule's positive and negative form — plain aggregates, division shapes,
BLANK comparisons, IF/SWITCH stairs, iterators (nested and single-column),
VAR blocks, ALL filters, IFERROR, EARLIER, and lowercase calls. The model
benchmark instantiates the corpus four times as tables `T0..T3`.

Reproduce with:

```
python examples/bench_rules.py
```

## Per-rule cost

Mean time per expression per rule, 50 rounds over the corpus
(macOS, CPython 3.12, aibi-dax 0.2.1):

| Rule                      | µs/expr |
| ------------------------- | ------: |
| `calculate_inside_iterator` |   2.4 |
| `raw_division`              |   3.2 |
| `lowercase_function`        |   1.9 |
| `too_many_ifs`              |   1.7 |
| `single_column_iterator`    |   1.7 |
| `concat_ampersand`          |   1.7 |
| `bare_all_table`            |   1.7 |
| `iferror_overuse`           |   1.7 |
| `nested_iterators`          |   1.7 |
| `blank_comparison`          |   1.6 |
| `switch_missing_default`    |   1.5 |
| `all_first_argument`        |   1.2 |
| `earlier_var`               |   0.9 |
| `values_with_hasonevalue`   |   0.4 |

## Pipeline cost

| Stage            | Before memoization | Current |
| ---------------- | -----------------: | ------: |
| `lint_expression` |        202 µs/expr | 25 µs/expr |
| `lint_model`      |       17.8 ms/model | 2.2 ms/model |

The ~8× gain comes from one change: `parse()` is memoized
(`lru_cache`, 512 entries). Every AST-driven rule parses the expression
it inspects, so without the cache one `lint_expression` call reparsed the
same string once per rule. Trees are frozen dataclasses, so sharing them
across rules and calls is safe.

## Notes for contributors

- Bench numbers are machine-dependent; treat tables here as relative
  comparisons, not absolute promises.
- Add the corpus form for any new rule to `CORPUS` in
  `examples/bench_rules.py` and re-run the bench before adding a row here.
- The docs smoke tests pin CLI output, not performance numbers — timing
  drift alone will not fail CI, but a large regression should open an
  issue rather than a silent docs edit.
