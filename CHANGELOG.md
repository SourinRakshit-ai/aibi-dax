# Changelog

## 0.2.2 - 2026-11-18

- Published to PyPI via trusted publishing (OIDC) — `pip install
  aibi-dax`. Tag `v0.2.1` ships the first release.
- Docs: README restructured to what/how/why/use-cases, install
  section switched to `pip install aibi-dax`; docs site and CI
  recipes ship the same install command.

## 0.2.1 - 2026-11-12

- Rule 46: `DIVIDE(x, 0)` (→ BLANK, or the alternate directly)
- Rule 45: complementary boolean operands (`x || NOT(x)`, `x && NOT(x)`) collapse to TRUE/FALSE.
- Published to PyPI via trusted publishing (OIDC). `pip install aibi-dax`.
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
  `= FALSE()` → `NOT col`); rule 28 flags
  `DISTINCTCOUNT(VALUES(col))` (→ `DISTINCTCOUNT(col)`);
  rule 29 flags `IF(cond, x, x)` (→ `x`; branches compared with
  DAX's case rules and numbers by value); rule 30 flags
  `SUMX(t, k)` with a constant `k` (→ `COUNTROWS(t) * k`);
  rule 31 flags `[x] <> BLANK()` (→ `NOT(ISBLANK(x))`);
  rule 32 flags `TRIM(TRIM(x))` (→ `TRIM(x)`); rule 33 flags
  `FILTER(t, TRUE())` (→ `t`); rule 34 flags `x * 1` / `1 * x` /
  `x / 1` (→ drop the operation — additive zero is deliberately not
  flagged; see the Fix bullet); rule 35 flags nested idempotents
  (`UPPER(UPPER(x))`, `LOWER`, `ABS`, `INT`) — one call suffices;
  rule 36 flags `COUNTX(t, k)` with a constant `k` (→
  `COUNTROWS(t)`; `COUNTAX` too); rule 37 flags `POWER(x, 1)` (→
  `x`) and `POWER(x, 0)` (→ `1`); rule 38 flags `OR(TRUE(), x)` (→
  `TRUE()`) and `AND(FALSE(), x)` (→ `FALSE()`), call and
  `||`/`&&` forms; rule 39 flags `COALESCE(..., BLANK())` (→
  drop the trailing alternative) and single-argument `COALESCE(x)`
  (→ `x`); rule 40 flags a branch-nested IF whose predicate matches
  the outer one (→ collapse; rule 29's canonical signature);
  rule 41 flags `IF(TRUE(), x, y)` (→ `x`) and `IF(FALSE(), x, y)`
  (→ `y`); rule 42 flags `COALESCE(..., x, ..., x)` (→ the duplicate
  is unreachable; drop it); rule 43 flags `c && c`, `c || c`,
  `AND(c, c)`, `OR(c, c)` (→ keep one); rule 44 flags
  `SUMX(t, IF(c, 1, 0))` (→ `COUNTROWS(FILTER(t, c))`).
- Fix: rule 20 (`if_isblank_coalesce`) special-cases a zero-argument
  `BLANK()` yes-branch — `IF(ISBLANK(x), BLANK(), x)` — and now says
  the IF collapses to `x` directly, instead of suggesting
  `COALESCE(x, BLANK())`, which rule 39 then reduces to the same thing.
  The negated twin `IF(NOT(ISBLANK(x)), x, BLANK())` (and the `!`-spelling)
  collapses the same way.
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
  `dxa parse` gains the `^` exponentiation operator: bindingest in the
  ladder, right-associative, tighter than unary minus (`-2 ^ 2` is
  `-(2 ^ 2)`, like DAX/Python); rule 37 (`power_identity`) extends to
  `[x] ^ 1` / `[x] ^ 0`;
  `dxa metrics --top N` keeps the N heaviest expressions by weight,
  reported heaviest-first (ties keep argument order) — the
  expression-side twin of `rank --top`; below 1 exits 2.
  `dxa lint --sarif` prints a SARIF 2.1.0 document for CI code
  scanning (rule attribution, `--list-rules` summaries for the
  driver's rule descriptions, exit 0 whether or not findings exist);
  `dxa lint-model --sarif` is the whole-model equivalent — one result
  per finding, each with a `locations[]` JSON Pointer into the measure
  (RFC 6901 escaped), mutually exclusive with `--json`/`--summary`,
  exit 0;
  findings now carry rule names via `lint_findings`, with
  `lint_expression` as a thin projection.
- Fix: rule 34 (`identity_arithmetic`) no longer flags `[x] + 0` /
  `0 + [x]` / `[x] - 0` — BLANK converts to 0 in sums and subtractions,
  so additive zero is the documented way to display blank measures as
  zeros, not noise. The rule now covers the multiplicative identities
  only (`x * 1`, `1 * x`, `x / 1`), which hold for blanks (BLANKs
  propagate in multiplication and division).
- Docs: new CI integration page — exit-code contract and a GitHub
  Actions SARIF workflow (`--file -` + `upload-sarif`), plus the
  plain-`--json` idiom; every CLI fence on the page is replayed by a
  docs test.
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
