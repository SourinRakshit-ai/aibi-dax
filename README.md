# aibi-dax

*dxa* — DAX expression analysis: complexity metrics, anti-pattern detection
and per-model ranking. Companion to [aibi-toolkit](https://github.com/SourinRakshit-ai/aibi-toolkit):
where the toolkit checks the model *around* your measures (naming, formats,
hygiene), aibi-dax checks the expressions *inside* them.

[![CI](https://github.com/SourinRakshit-ai/aibi-dax/actions/workflows/ci.yml/badge.svg)](https://github.com/SourinRakshit-ai/aibi-dax/actions/workflows/ci.yml)
[![Lint](https://github.com/SourinRakshit-ai/aibi-dax/actions/workflows/lint.yml/badge.svg)](https://github.com/SourinRakshit-ai/aibi-dax/actions/workflows/lint.yml)
[![Python](https://img.shields.io/badge/python-3.10–3.13-blue)](pyproject.toml)
[![Types](https://img.shields.io/badge/mypy-strict-blue)](pyproject.toml)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](.github/workflows/lint.yml)

```bash
pip install .
dxa --version
```

## Commands

| Command                    | What it does                                   |
| -------------------------- | ---------------------------------------------- |
| `dxa metrics "EXPR"`       | token/function/depth/iterator counts + weight  |
| `dxa metrics "EXPR" --json`| the same as a JSON payload                     |
| `dxa rank model.json`      | heaviest measures first (`--top N`, `--table T`) |
| `dxa lint "EXPR"`          | anti-pattern findings for one expression (`--json`) |
| `dxa lint-model model.json`| findings across every measure (`--table T`, `--json`) |
| `dxa parse "EXPR"`         | the recursive-descent AST, human or `--json`    |

Model dumps use the same JSON shape TMDL export produces — the shared schema
of aibi-toolkit — so one file feeds both tools.

## Anti-patterns detected

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

## What the weight measures

`weight = tokens + 3·functions + 5·depth + 20·iterators` — iterators cost the
most because row context is where DAX quietly goes wrong.

## Development

```bash
pip install -e ".[dev]"
make test        # pytest
make typecheck   # mypy --strict src/aibi_dax/
make lint        # ruff check src/ tests/
```

MIT licensed. Roadmap lives in the issue tracker.
