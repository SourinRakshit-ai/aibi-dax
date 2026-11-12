# Contributing to aibi-dax

Thanks for considering a contribution. The project is small on purpose:
one CLI (`dxa`), one parser, one rule engine. Everything below keeps it
that way.

## The three gates

Every change must pass all three, run separately, before you commit:

```
python3 -m pytest -q                     # tests (also the docs smoke tests)
python3 -m mypy --strict src/aibi_dax/   # full strict typing
python3 -m ruff check src/ tests/        # lint
```

CI enforces the same three plus a coverage floor:

```
python3 -m pytest --cov=src/aibi_dax --cov-fail-under=95 -q
```

A change that only passes when chained with `&&` has not passed.

## What belongs here

- **New anti-pattern rules** — an AST-driven check in
  `src/aibi_dax/antipattern.py`, registered in `ALL_RULES`, with tests
  covering the flagged and clean forms, a docs entry in
  `docs/rules.md`, and its corpus form added to
  `examples/bench_rules.py`.
- **Parser/lexer fixes** — behavior changes need a failing test first.
  Error messages must keep the `near 'tok' at char N` shape (issue #12).
- **CLI additions** — every flag needs: a `docs/CLI.md` section, a
  byte-for-byte smoke test in `tests/test_docs.py`, and entries in the
  README and `docs/index.md` command tables. The docs fences are the
  public contract; drift fails CI, not a review comment.
- **Performance claims** — numbers go in `docs/performance.md` with a
  reproducible benchmark, never in prose alone.

## Versioned releases

Releases go through a release branch (`release/X.Y.Z`) and a squash
PR so CI runs on the exact tree that ships. `CHANGELOG.md` must be
updated in the same PR; `tests/test_docs.py` ties `--version` fences
and the version guard to `pyproject.toml`.

## Commit style

Short imperative subjects: `feat:`, `fix:`, `docs:`, `test:`,
`perf:`, `chore:`. Reference issues with `(closes #N)` in the body or
subject so they auto-close.

## Local docs check

```
python3 -m mkdocs build --strict && rm -rf site
```
