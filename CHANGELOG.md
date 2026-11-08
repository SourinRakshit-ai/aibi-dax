# Changelog

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
