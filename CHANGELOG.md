# Changelog

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
