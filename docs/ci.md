# Continuous integration

`dxa` is a single binary you can install anywhere Python runs, so the
lint step is a drop-in for any CI system. This page shows the exit-code
contract and a GitHub Actions workflow; the same steps work in any
runner that can `pip install` a package.

## The exit-code contract

| Exit | Meaning |
|------|---------|
| 0 | clean (or, with `--sarif`, whatever the document says) |
| 1 | findings exist |
| 2 | usage error — bad flag, unknown rule, unreadable file |

```
$ dxa lint "SUM('Sales'[Amount])"
no findings
```

A failing run prints one `-` line per finding on stdout and exits 1, so
`set -e` fails the job while you read the messages in the log.

## GitHub Actions with SARIF upload

`dxa lint --sarif` emits a [SARIF 2.1.0](CLI.md) document; GitHub's
`upload-sarif` action files each finding in the Security tab like a
CodeQL alert, with the rule id and message you see locally. The
workflow installs a release, lints a measure file, and uploads the
result. For a whole model, `dxa lint-model model.json --sarif` does
the same with one `result` per finding, each carrying a `locations[]`
JSON Pointer into the measure —
`model.json#/tables/Sales/measures/Iterator Calc` — so the Security
tab groups findings back to the measure they came from:

```yaml
name: dax-lint
on: [push, pull_request]
permissions:
  security-events: write   # required by upload-sarif
jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.13" }
      - run: pip install git+https://github.com/SourinRakshit-ai/aibi-dax.git@v0.2.1
      - name: Lint the measure
        run: cat measure.dax | dxa lint --file - --sarif > results.sarif
      - uses: github/codeql-action/upload-sarif@v3
        with: { sarif_file: results.sarif }
```

Notes:

- `cat measure.dax | dxa lint --file - --sarif` lints one measure and
  writes the document; the exit code is 0 either way, so the upload
  step always runs. Usage errors (a missing flag, an unknown `--rule`)
  still exit 2 and fail the job before upload.
- SARIF findings carry `ruleId`s matching `dxa lint --list-rules`, so
  the Security tab groups them per rule.
- Extend with a `--rule` filter if the team wants only a subset
  enforced, e.g. `dxa lint --file - --rule raw_division --sarif`.
- `--json` and `--sarif` are mutually exclusive (exit 2).

## A plain gate

If you do not want the Security tab, the plain form is the gate
itself — exit 1 fails the step when findings exist:

```yaml
      - run: pip install git+https://github.com/SourinRakshit-ai/aibi-dax.git@v0.2.1
      - run: dxa lint --file measure.dax
```

`--json` is for tooling that consumes the findings programmatically —
it prints the same messages as a JSON array, `[]` when clean:

```
$ dxa lint "SUM('Sales'[Amount])" --json
[]
```

Use `--sarif` when you want findings tracked over time; the exit
code alone when you just want to block the merge.

## Where to go next

- [CLI reference](CLI.md) — every flag and exit code in one place.
- [Cookbook](recipes.md) — fixing flagged measures, one recipe at a
  time.
