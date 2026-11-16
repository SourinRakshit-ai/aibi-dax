# CLI reference — `dxa`

## Global

```
dxa --version        # dxa 0.2.1
dxa --help
```

## `dxa --completions bash|zsh|fish`

Prints a completion script on stdout and exits 0 — subcommands, every
flag, and rule names after `--rule` / for `explain`. The scripts are
generated from the parser itself, so they cannot drift from the real
CLI. An unknown shell (or none) exits 2 with usage and the three names:

```
$ dxa --completions tcsh
usage: dxa [-h] [--version] [--completions [SHELL]]
           {metrics,rank,explain,lint,lint-model,parse} ...
dxa: error: unsupported shell 'tcsh' — one of: bash, zsh, fish
```

Install by writing the script where the shell looks for it:

- **bash** — `dxa --completions bash > ~/.local/share/bash-completion/completions/dxa`
  (needs `bash-completion` loaded)
- **zsh** — `dxa --completions zsh > ~/.zfunc/_dxa`, with `fpath=(~/.zfunc $fpath)`
  before `compinit`; or straight into the current shell with
  `source <(dxa --completions zsh)`
- **fish** — `dxa --completions fish > ~/.config/fish/completions/dxa.fish`

## `dxa metrics "EXPR"`

Prints six aligned metrics plus the composite weight:

```
$ dxa metrics "SUMX('Sales', CALCULATE([Amount]))"
tokens      9
lines       1
chars       34
functions   2
depth       2
iterators   1
weight      45
```

`--json` wraps the same payload: `{"metrics": {...}, "weight": 45}`.
`--file PATH` reads the expression from a file (`-` for stdin), matching
`dxa lint`.

Several expressions may be given at once — one block each, in argument
order, every one validated before anything is printed:

```
$ dxa metrics "SUM('Sales'[Amount])" "SUMX('Sales', CALCULATE([Amount]))"
expr: SUM('Sales'[Amount])
tokens      5
lines       1
chars       20
functions   1
depth       1
iterators   0
weight      13

expr: SUMX('Sales', CALCULATE([Amount]))
tokens      9
lines       1
chars       34
functions   2
depth       2
iterators   1
weight      45
```

With `--json` a multi-expression run emits `{"results": [{"expr",
"metrics", "weight"}, ...]}` in argument order; a single expression
keeps the one-object payload shown above. `--file` always supplies
exactly one expression, and mixing it with positionals exits 2.

## `dxa rank model.json [--top N] [--min-weight W]`

Weighs every measure in a shared-schema model dump:

```
$ dxa rank model.json --top 3
    57  Sales.Iterator Calc
    34  Sales.If Stair
    12  Sales.Clean Total
```

`--min-weight 40` keeps only measures at or above that weight, which is
the review question "what crosses the line"; `--top N` then applies to
the filtered set. It composes with `--table` — which matches table
names case-insensitively — and `--json`. The model
path may be `-` to read the dump from stdin.

## `dxa lint "EXPR"`

Anti-pattern findings for one expression. Exit code 0 when clean, 1 with
`-` lines per finding. `--json` prints the findings as a JSON list (`[]`
when clean). `--rule NAME` runs one rule (function name) and may be
repeated to run several — findings are the union; exit 2 with
the rule list on stderr if any name is unknown. `--list-rules` prints the rule
inventory with each rule's summary and exits 0. `--list-rules --json`
prints that inventory as `[{"name": …, "summary": …}]` for editor
plugins and CI allow-lists. `--file PATH` reads the
expression from a file instead, so a measure copied from a model keeps
its newlines and quotes; `--file -` reads stdin, so
`cat measure.dax | dxa lint --file -` works in a pipeline. Pass one
source or the other, never both. A blank expression — nothing, or only
whitespace, from any source — exits 2 with `got an empty expression
from …` rather than passing silently:

```
$ dxa lint "IF(a, 1, IF(b, 2, IF(c, 3, [D]/[E])))"
- 3 nested IF calls — SWITCH(TRUE(), ...) reads better and evaluates faster.
- Raw '/' division — use DIVIDE(num, den) to absorb zero-denominator errors.
(exit 1)
```

## `dxa explain [RULE]`

Full documentation for one rule — its docstring, underlined. With no
argument, prints the rule inventory (the same name + summary lines as
`dxa lint --list-rules`) followed by a hint, and exits 0 — `--json`
then emits the same JSON array `--list-rules --json` does. Exit 2 with
the complete rule list on stderr if the name is unknown. Names match
case-insensitively and ignore surrounding whitespace; the heading always
prints the canonical lower-case name. `--json` emits
`{"name", "summary", "doc"}` — the same summary as `--list-rules --json`
and the docstring without the heading, for editor hovers:

```
$ dxa explain earlier_var
earlier_var
-----------
EARLIER is superseded by VAR capture — flat and type-checkable.
```

## `dxa lint-model model.json`

Groups findings by `table.measure`; `--table T` restricts to one table,
matched case-insensitively.
`--rule NAME` runs one rule (function name) and may be repeated to run
several — findings are the union; exit 2 with the rule list
on stderr if any name is unknown. Prints nothing and exits 0 for a clean model.
Findings exit 1 with `- ` lines per finding; `--json` prints the findings
map. Both model commands (`lint-model` and `rank`) share one loader, so
a missing file, broken JSON or a non-object payload exits 2 with a
single-line reason — `cannot read …`, `is not valid JSON: …`,
`is not a model dump: …` — never a traceback. Passing `-` as the path
reads the model JSON from stdin instead (`tmdlexport | dxa lint-model -`),
and the same errors then name `stdin` rather than a path.

`--summary` swaps the per-measure listing for a model-wide rule
histogram — the count of measures each rule fires on, heaviest first.
It respects `--table` and `--rule`, and `--json` emits the counts as an
object. Exit 1 when anything fires, 0 with `model is clean` otherwise:

```
$ dxa lint-model model.json --summary
    2  calculate_inside_iterator
    1  raw_division
```

## `dxa parse "EXPR"`

Reduces the expression to an AST (recursive descent; exit 2 on a
genuinely unparseable sequence). `--json` prints the tree as JSON;
`--file PATH` reads the expression from a file instead of the command
line (`-` for stdin), so multiline measures keep their shape. `--tree` prints it one
node per line, children indented, with `field:`
labels where position alone would not say what the child is:

```
$ dxa parse "1 + [A]" --tree
Binary op='+'
  left:
    Literal text='1'
  right:
    ColumnRef name='A'
```

```
$ dxa parse "1 + [A]" --json
{
  "op": "+",
  "left": {
    "text": "1"
  },
  "right": {
    "name": "A"
  }
}
```

Unparseable sequences exit 2 with a `parse error:` message on stderr.
A missing quote or bracket names the delimiter and where it opened
(`unterminated string starting at char 4`), and doubled delimiters are
escapes, not closers (`"a""b"`, `'T''x'`, `[A]]]]]`).

The grammar covers `VAR … RETURN` blocks, calls, qualified columns,
list literals, and the operator ladder `||`, `&&`, comparison/`IN`,
`+ -`, `&`, `* /`, unary. `IN` binds with the comparisons, and its
right side is usually a list. Unary operators are `- + !` and the
keyword `NOT` (either case), so `NOT ISBLANK([x])`, `NOT ([a] = 1)`
and `[a] && NOT [b]` parse. Table qualifiers may be quoted or bare
(`'Sales'[Amount]`, `Sales[Amount]`):

```
$ dxa parse "[k] IN {1, 2}" --tree
Binary op='IN'
  left:
    ColumnRef name='k'
  right:
    List
      Literal text='1'
      Literal text='2'
```
