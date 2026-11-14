# aibi-dax

*dxa* — DAX expression analysis: complexity metrics, anti-pattern detection
and per-model ranking. Companion to [aibi-toolkit](https://github.com/SourinRakshit-ai/aibi-toolkit):
where the toolkit checks the model *around* your measures (naming, formats,
hygiene), aibi-dax checks the expressions *inside* them.

## Quick start

```bash
pip install .
dxa --version
```

## Commands

| Command | Purpose |
|---|---|
| `dxa metrics "EXPR"` | six complexity metrics plus a single weighted score (`--file`) |
| `dxa rank model.json --top N` | the most complex measures of a model dump |
| `dxa lint "EXPR"` | anti-pattern findings for one expression (`--rule`, `--list-rules [--json]`, `--file`) |
| `dxa explain RULE` | full documentation for one anti-pattern rule |
| `dxa lint-model model.json` | findings across every measure, grouped (`--table`, `--rule`, `--summary`) |
| `dxa parse "EXPR"` | the recursive-descent AST, human or `--json` (`--file`) |

## The weight

`weight = tokens + 3·functions + 5·depth + 20·iterators` — iterators cost the
most because row context is where DAX quietly goes wrong.

See the [seventeen anti-pattern rules](rules.md) for what the linter flags and why.
