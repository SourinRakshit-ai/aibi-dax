# Changelog

## 0.2.1 - 2026-11-12

- Rules 1 and 14: `calculate_inside_iterator` rewritten over the AST
  (string-literal mentions no longer fire), and new rule 14 — a
  single-column row iterator (`SUMX('S', 'S'[Amount])`) collapses to a
  plain aggregate. Rule 15 flags `ABS(x)` against an impossible bound;
  rule 16 flags `IF(cond, TRUE(), FALSE())` (→ `cond`, inverted → `NOT cond`);
  rule 17 flags `FILTER(...)` as an aggregate's first argument
  (→ pass the condition to `CALCULATE`); rule 18 flags a nested
  `CALCULATE(CALCULATE(...))` whose inner context transition is
  redundant (→ merge the filter lists into one call); rule 19 flags
  `COUNTROWS(VALUES(col))` (→ `DISTINCTCOUNT(col)`); rule 20 flags
  `IF(ISBLANK(x), y, x)` (→ `COALESCE(x, y)`); rule 21 flags a
  computed argument inside `SUMMARIZE` (→ group with `SUMMARIZE`,
  compute with `ADDCOLUMNS`); rule 22 flags
  `IF(ISERROR(x), y, x)` (→ `IFERROR(x, y)`); rule 23 flags an
  `AND(...)` (or `&&`) filter argument inside `CALCULATE` (→ pass
  each conjunct as its own argument — `CALCULATE` already ANDs
  them); rule 24 flags a `VAR` never referenced before `RETURN`
  (→ drop the dead binding or use it); rule 25 flags
  `COUNTROWS(t) = 0` (→ `ISEMPTY(t)`; `<> 0` / `> 0` →
  `NOT(ISEMPTY(t))`); rule 26 flags `NOT(NOT(x))` (→ `x`);
  rule 27 flags `[flag] = TRUE()` (→ the column itself;
  `= FALSE()` → `NOT col`).
- `--table` on `rank` and `lint-model` matches table names
  case-insensitively (one shared filter): `--table sales` now finds
  `Sales` instead of silently reporting nothing — or, for
  `lint-model`, "model is clean" over findings that exist. A table
  whose name is not a string never matches.
- CLI: `dxa parse --tree` (indented AST), `dxa lint --rule` and
  `dxa lint-model --rule` to run one rule (exit 2 + rule list on stderr
  when unknown), `dxa lint --file PATH` to read a multiline measure from
  disk, and `dxa lint-model --summary` for a model-wide rule histogram.
  `dxa lint --list-rules --json` emits the rule inventory as
  `[{"name", "summary"}]` for tooling; `dxa metrics --file` and
  `dxa parse --file` share the same resolver (`--file -` reads stdin),
  and `dxa explain` matches rule names case-insensitively.
  `dxa explain` with no argument now prints the rule inventory
  (name + summary, with a hint to pass a rule) instead of dying on
  an argparse error; `--json` emits the `--list-rules` array.
- CLI: `dxa rank --min-weight W` keeps only measures at or above the
  threshold, with `--top N` applying to the filtered set. A blank
  expression (including a blank `--file`/stdin) now exits 2 on
  `lint`/`metrics`/`parse` instead of passing lint silently.
- CLI: `dxa explain --json` emits `{"name", "summary", "doc"}` for
  editor hovers, sharing the summary with `--list-rules --json`.
- CLI: `--rule` repeats on `lint` and `lint-model` (and `--summary`) —
  findings are the union of the named rules; an unknown name anywhere in
  the list exits 2 before any output.
- CLI: `dxa --completions bash|zsh|fish` prints a tab-completion script
  generated from the parser's own structure (subcommands, flags, rule
  names), so it cannot drift; an unknown or missing shell exits 2 with
  usage. `dxa` with no subcommand keeps argparse's exact error text.
- CLI: `dxa metrics` accepts several expressions at once — one block
  each in argument order (`--json` wraps them as `{"results": [...]}`);
  a single expression keeps its exact old output, `--file` still means
  one measure, and every positional is validated before any output.
- Model loading: `dxa rank` and `dxa lint-model` report a missing file,
  broken JSON or a non-object payload as a one-line exit-2 error
  instead of a Python traceback, and both accept `-` to read the model
  JSON from stdin.
- Lexer/parser: `]]` bracket escapes inside column names; parse errors
  carry the source character offset; `IN { … }` list literals parse as a
  comparison-level binary with a `List` right side; unquoted table
  qualifiers (`Sales[Amount]`) parse the same as quoted ones; a missing
  quote or bracket reports `unterminated … starting at char N` instead
  of blaming the text after it, and doubled delimiters are escapes. The
  keyword `NOT` parses as a unary operator alongside `!`.
- Perf: `parse` memoized — `lint_expression` 202 → 25 µs,
  `lint_model` 17.8 → 2.2 ms on the benchmark corpus.
- Chore: Dependabot for pip + GitHub Actions. 173 tests, coverage ≥ 95%.

## 0.2.0 - 2026-11-11

- Parser: `VAR … RETURN` assignment blocks, chained `VAR`s, and
  fully-qualified `'Table'[Column]` references (`QualifiedColumn` node);
  `dxa parse` emits them all.
- Rule 13: `SWITCH` without a default case flags the silent-BLANK
  fall-through; argument parity checked on the AST.
- Rule walkers descend `Var` blocks, so iterator nesting and IF counts
  inside `VAR` bodies are visible.
- CLI: `--json` for `dxa lint`; `--table` filter for `dxa lint-model`.
- CI: coverage job installs editable so measured paths match imports
  (the regular install made coverage read 0.00%); publish workflow
  fixed to job-scoped `environment` for trusted publishing.
- Docs: rule 13 reference, parse examples pinned by smoke tests,
  `examples/parse_tour.py`. 66 tests, coverage ≥ 95%.

## 0.1.1 - 2026-11-08

- CLI: `--json` flag for `dxa rank` and `dxa lint-model` (machine-readable
  payloads, same exit-code contract as the human output).
- Lint: shared `ruff.toml` (line length 100, target py310) matching the
  aibi-toolkit configuration.
- Build: `coverage` Makefile target with pytest-cov added to the dev extras —
  currently 97% on 37 tests.
- Docs: CI/Lint/Python/Types/Ruff badges mirroring the toolkit's README row.

## 0.1.0 - 2026-11-08

- First release of `dxa`, the DAX-analysis companion to aibi-toolkit.
- Analysis core: DAX tokenizer, complexity metrics (tokens, functions,
  nesting depth, iterator count) and a single weighted score with
  per-model ranking.
- Six anti-pattern rules in the first cut, grown to eleven before 0.1.0:
  CALCULATE-inside-iterator, IF stairs, raw division, `= BLANK()`,
  bare `ALL(table)`, `&` in CONCATENATEX, `EARLIER(...)` deprecation,
  `ALL`-as-first-argument aggregates, `IFERROR` overreach,
  `HASONEVALUE`+`VALUES` pairs, and lowercase function calls.
- CLI: `dxa metrics|rank|lint|lint-model` with human and JSON output.
- CI on Python 3.10–3.13 (plus macOS on 3.13); mypy --strict and ruff
  gates pinned to trusted action SHAs.
- Quality: 35 tests, full strict typing, ruff-clean.
