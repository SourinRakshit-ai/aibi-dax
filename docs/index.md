# aibi-dax

*dxa* — DAX expression analysis: complexity metrics, anti-pattern detection
and per-model ranking. Companion to [aibi-toolkit](https://github.com/SourinRakshit-ai/aibi-toolkit):
where the toolkit checks the model *around* your measures (naming, formats,
hygiene), aibi-dax checks the expressions *inside* them.

## Quick start

```bash
pip install aibi-dax
dxa --version
```

Or install from the source tree: `pip install .`.

## Commands

| Command | Purpose |
|---|---|
| `dxa metrics "EXPR"` | six complexity metrics plus a single weighted score (repeatable; `--file`; `--top N` keeps the N heaviest) |
| `dxa rank model.json --top N` | the most complex measures of a model dump (`--min-weight W`; `-` = stdin) |
| `dxa lint "EXPR"` | anti-pattern findings for one expression (`--rule`, `--list-rules [--json]`, `--file`, `--sarif`) |
| `dxa explain [RULE]` | full documentation for one anti-pattern rule; no argument lists them all (`--json`) |
| `dxa lint-model model.json` | findings across every measure, grouped (`--table` any case, `--rule`, `--summary`, `--sarif`; `-` = stdin) |
| `dxa parse "EXPR"` | the recursive-descent AST, human or `--json` (`--file`) |
| `dxa --completions shell` | bash/zsh/fish tab-completion script, generated from the parser |

## The weight

`weight = tokens + 3·functions + 5·depth + 20·iterators` — iterators cost the
most because row context is where DAX quietly goes wrong.

See the [forty-seven anti-pattern rules](rules.md) for what the linter flags and why, the [cookbook](recipes.md) for whole measures going from flagged to clean, and [CI integration](ci.md) for running the linter in a pipeline.
