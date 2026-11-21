# aibi-dax

*dxa*, a DAX expression analysis CLI: complexity metrics, anti-pattern
detection and per-model ranking. Companion to
[aibi-toolkit](https://github.com/SourinRakshit-ai/aibi-toolkit):
where the toolkit checks the model around your measures (naming,
formats, hygiene), aibi-dax checks the expressions inside them.

[![CI](https://github.com/SourinRakshit-ai/aibi-dax/actions/workflows/ci.yml/badge.svg)](https://github.com/SourinRakshit-ai/aibi-dax/actions/workflows/ci.yml)
[![Lint](https://github.com/SourinRakshit-ai/aibi-dax/actions/workflows/lint.yml/badge.svg)](https://github.com/SourinRakshit-ai/aibi-dax/actions/workflows/lint.yml)
[![Python](https://img.shields.io/badge/python-3.10–3.13-blue)](pyproject.toml)
[![Types](https://img.shields.io/badge/mypy-strict-blue)](pyproject.toml)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](.github/workflows/lint.yml)

## Why this exists

A DAX measure is a formula inside a formula engine. The syntax is small,
the semantics are deep, and most mistakes compile fine and return a
wrong number quietly. The failures that hurt are the ones nobody sees in
code review: an iterator that shadows the filter context, a `DIVIDE`
missing where a raw `/` hides behind a passing test, a dead `VAR`
nobody deletes, a BLANK where zero was expected.

That problem does not print itself in an error message, and it does not
announce itself in a visual either. It shows up as a measure that is
harder to review but still "works". aibi-dax reads the expression and
reports what it sees: how complex it is, and which known ways of being
wrong it trips on.

## What it does

1. **Scores complexity** with one number you can sort on:
   `weight = tokens + 3·functions + 5·depth + 20·iterators`. Weighted so an
   iterator costs more than a function costs more than a token, because
   row context is where DAX quietly goes wrong.
2. **Flags 44 documented anti-patterns**, each with a fix hint and a
   reason it fires. AST-driven rules, not regex: comments are blanked
   before the rules see the text, and string literals never trip a rule
   that fires on structure.
3. **Ranks a whole model dump** by measure weight, so review happens on
   the three measures that matter instead of all sixty.
4. **Fits CI** with stable exit codes (0 clean, 1 findings, 2 usage
   error) and SARIF output for code scanning.

## How to use it

Install from PyPI and check the binary works:

```bash
pip install aibi-dax
dxa --version
```

Or install from the source tree: `pip install .`.

Score one expression (the weight is the number you sort on):

```bash
$ dxa metrics "SUMX('Sales', CALCULATE([Amount]))"
tokens      9
lines       1
chars       34
functions   2
depth       2
iterators   1
weight      45
```

Lint one expression (exit 1 when anything is found, so `set -e` fails
the job):

```bash
$ dxa lint "IF(a, 1, IF(b, 2, IF(c, 3, [D] / [E])))"
- 3 nested IF calls — SWITCH(TRUE(), ...) reads better and evaluates faster.
- Raw '/' division — use DIVIDE(num, den) to absorb zero-denominator errors.
```

Rank the heaviest measures in a model dump (the JSON shape the TMDL
export produces, so one file feeds both tools). Point it at a file or
pipe it via stdin:

```bash
dxa rank model.json --top 3
tmdlexport | python -c "import sys, json; print(json.dumps(...))" > model.json
dxa lint-model model.json --sarif > results.sarif
cat measure.dax | dxa lint --file -
```

Everything is also `--json` for your own tooling, and the exit codes
are the contract: `0` clean or informational, `1` findings, `2` usage
error.

## How it helps

- **Review honestly reads real code.** Rank sorts measures by weight,
  so the gnarly ones land in front of a reviewer instead of after the
  easy ones. Iterator-dense measures are where filter-context bugs
  live, and they are the ones the weight favors.
- **Findings are actionable.** Every rule says what it saw, why it is
  usually wrong, and the rewrite: `DIVIDE` absorbs zero denominators,
  capture the outer row in a `VAR` instead of `EARLIER`, drop the dead
  variable. No "consider refactoring for readability" hedges.
- **CI gates on what code review misses.** `dxa lint` exits 1 on any
  finding; `--sarif` files them in the Security tab of your host with
  the same rule ids as `--list-rules`. The docs site documents a
  GitHub Actions workflow for both paths.
- **The error semantics are taught, not memorized.** Rules encode the
  BLANK-vs-zero traps, iterator shadowing and uninitialized `VAR`
  bindings directly; each rule message is a one-line refresher for why
  the pattern is wrong.

## What it is not

- **Not a DAX evaluator.** It never computes a result. It reads
  expressions with a recursive-descent parser and reports structural
  patterns. Behavior is checked by the tests and by your own runs, as
  with a linter for anything else.
- **Not tied to Power BI.** Any DAX-flavored text parses, whether it
  came from an `.xx` model, TMDL exports or a notebook cell. Flag
  semantics come from DAX, not from a live server.
- **Not a style checker.** It flags patterns that are wrong, risky or
  dead weight. It does not care about indentation, case of your own
  identifiers, or where you put your semicolons.
- **Not a substitute for evaluation and measurement.** It cannot tell
  you the measure is slow on data, or that your cardinality is the
  problem, or that a visual refresh is the bottleneck. Those come from
  performance analyzer and the toolkit, not from this.

## Commands

| Command | What it does |
| --- | --- |
| `dxa metrics "EXPR"` | token/function/depth/iterator counts + weight (repeatable; `--file PATH`; `--top N` keeps the N heaviest) |
| `dxa metrics "EXPR" --json` | the same as a JSON payload (`{"results": …}` for several expressions) |
| `dxa rank model.json` | heaviest measures first (`--top N`, `--table T` any case, `--min-weight W`; `-` = stdin) |
| `dxa lint "EXPR"` | anti-pattern findings for one expression (`--rule R`, `--list-rules [--json]`, `--file PATH`, `--sarif`) |
| `dxa explain [RULE]` | full documentation for one anti-pattern rule; no argument lists them all (`--json`) |
| `dxa lint-model model.json` | findings across every measure (`--table T` any case, `--rule R`, `--summary`, `--sarif`; `-` = stdin) |
| `dxa parse "EXPR"` | the recursive-descent AST, human or `--json` (`--file PATH`) |
| `dxa --completions shell` | bash/zsh/fish tab-completion script, generated from the parser |

Model dumps use the same JSON shape TMDL export produces (the shared
schema of aibi-toolkit), so one file feeds both tools.

<details>
<summary>44 anti-pattern rules detected (click to expand)</summary>

1. `CALCULATE` inside a row iterator (`SUMX`, `AVERAGEX`, …)
2. Three or more nested `IF` calls (→ `SWITCH(TRUE(), …)`)
3. Raw `/` division (→ `DIVIDE`, which absorbs zero denominators)
4. `= BLANK()` comparisons (→ `ISBLANK`)
5. Bare `ALL(table)` as a filter eraser (→ `REMOVEFILTERS`)
6. `&` concatenation inside `CONCATENATEX`
7. `EARLIER(...)` (→ capture the outer row with `VAR`)
8. `ALL`/`FILTER(ALL(...))` as an aggregate's first argument (→ boolean filters in `CALCULATE`)
9. `IFERROR` overreach (→ explicit error contracts)
10. `HASONEVALUE` + `VALUES` pairs (→ `SELECTEDVALUE`)
11. Lowercase function calls (→ UPPERCASE form)
12. Nested row iterators (→ `VAR` capture of the outer step)
13. `SWITCH` without a default (→ explicit else argument)
14. Single-column row iterator (→ plain `SUM`/`AVERAGE`/`COUNT`/`MIN`/`MAX`)
15. `ABS(...)` against an impossible bound (→ sign check / drop the condition)
16. `IF(cond, TRUE(), FALSE())` (→ `cond`; inverted order → `NOT cond`)
17. `FILTER(...)` as an aggregate's first argument (→ the filter condition in `CALCULATE`)
18. `CALCULATE(CALCULATE(...))` (→ merge both filter lists into one `CALCULATE`)
19. `COUNTROWS(VALUES(col))` / `COUNTROWS(DISTINCT(col))` (→ `DISTINCTCOUNT(col)`)
20. `IF(ISBLANK(x), y, x)` (→ `COALESCE(x, y)`; special case for BLANK() yes/else branches)
21. `SUMMARIZE` with a computed argument (→ group with `SUMMARIZE`, compute with `ADDCOLUMNS`)
22. `IF(ISERROR(x), y, x)` (→ `IFERROR(x, y)`)
23. `AND(...)` as a `CALCULATE` filter argument (→ one filter argument per conjunct)
24. A `VAR` never referenced before `RETURN` (→ drop it or use it)
25. `COUNTROWS(t) = 0` (→ `ISEMPTY(t)`; `<> 0` / `> 0` → `NOT(ISEMPTY(t))`)
26. `NOT(NOT(x))` (→ `x`; the double wrapper cancels)
27. `[flag] = TRUE()` (→ the column itself; `= FALSE()` → `NOT col`)
28. `DISTINCTCOUNT(VALUES(col))` (→ `DISTINCTCOUNT(col)`)
29. `IF(cond, x, x)` (→ `x`; the predicate computes for nothing)
30. `SUMX(t, k)` with a constant (→ `COUNTROWS(t) * k`)
31. `[x] <> BLANK()` (→ `NOT(ISBLANK(x))`)
32. `TRIM(TRIM(x))` (→ `TRIM(x)`; one call is all it takes)
33. `FILTER(t, TRUE())` (→ `t`; the predicate keeps every row)
34. `x * 1`, `1 * x`, `x / 1` (→ drop the operation; `* 1` / `/ 1` hold for blanks; `+ 0` is the zero-forcing idiom and is not flagged)
35. `UPPER(UPPER(x))`, `ABS(ABS(x))`, `INT(INT(x))` (→ one call suffices)
36. `COUNTX(t, k)` with a constant (→ `COUNTROWS(t)`)
37. `POWER(x, 1)` (→ `x`), `POWER(x, 0)` (→ `1`), and the `^` forms
38. `OR(TRUE(), x)` (→ `TRUE()`), `AND(FALSE(), x)` (→ `FALSE()`)
39. `COALESCE(x, BLANK())` and `COALESCE(x)` (→ drop the trailing blank / the call)
40. `IF(c, …IF(c,…)…)` in-branch (→ collapse the nesting)
41. `IF(TRUE(), x, y)` (→ `x`) and `IF(FALSE(), x, y)` (→ `y`)
42. `COALESCE(x, x)` (→ drop the duplicate fall-through)
43. `c && c`, `c || c`, `AND(c, c)`, `OR(c, c)` (→ keep one)
44. `SUMX(t, IF(c, 1, 0))` (→ `COUNTROWS(FILTER(t, c))`)
45. `x || NOT(x)` / `x && NOT(x)` (→ `TRUE()` / `FALSE()`)
46. `DIVIDE(x, 0)` (→ BLANK, or the alternate directly)

</details>

## What the weight measures

`weight = tokens + 3·functions + 5·depth + 20·iterators`. It is not a
style metric; it is a review effort estimate. A deep iterator nesting
is the one thing you cannot eyeball, so it dominates the score.

## Docs and support

- **Docs site:** [https://sourinrakshit-ai.github.io/aibi-dax/](https://sourinrakshit-ai.github.io/aibi-dax/) (`mkdocs gh-deploy` from `docs/`)
- **Reference:** `docs/CLI.md` (flags, JSON shapes, exit codes), the
  rule index and reference in `docs/rules.md`, a
  [cookbook](docs/recipes.md) of before/after rewrites, and a
  [CI integration page](docs/ci.md) with a GitHub Actions SARIF
  workflow.
- **Issues:** [issue tracker](https://github.com/SourinRakshit-ai/aibi-dax/issues).
  Before filing, run `dxa lint "your expression"` so the rule names
  match the report.
- **Status:** [`aibi-dax`](https://pypi.org/project/aibi-dax/) is on
  PyPI (0.2.2), installed via `pip install aibi-dax`. Trusted
  publishing is set up with a pending publisher for this repo, so
  every release from here on ships the same way.

## Development

```bash
pip install -e ".[dev]"
python3 -m pytest -q                     # tests (docs smoke tests replay the CLI fences)
python3 -m mypy --strict src/aibi_dax/   # full strict typing
python3 -m ruff check src/ tests/        # lint
python3 -m pytest --cov=src/aibi_dax --cov-fail-under=95 -q   # coverage floor is 95
```

The gates are documented in [CONTRIBUTING.md](CONTRIBUTING.md), the
issue list and the [44 rules](docs/rules.md) live under the
[docs site](https://sourinrakshit-ai.github.io/aibi-dax/), and the
worked examples run as `examples/bench_rules.py` and friends.

MIT licensed. Roadmap lives in the issue tracker.
