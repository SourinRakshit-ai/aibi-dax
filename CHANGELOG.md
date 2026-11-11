# Changelog

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
