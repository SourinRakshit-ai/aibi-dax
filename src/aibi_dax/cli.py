"""Command-line interface for aibi-dax (`dxa`)."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, fields, is_dataclass
from pathlib import Path
from typing import TypeGuard

from . import __version__
from .antipattern import ALL_RULES, Rule, rule_summary
from .completions import SHELLS
from .completions import script as completion_script
from .complexity import rank_measures, report, weight
from .lint import (
    lint_expression,
    lint_findings,
    lint_model,
    lint_model_findings,
    lint_model_summary,
)
from .model_io import Model, load_model
from .parser import Node, ParseError, parse
from .sarif import build_model_sarif, build_sarif


def format_tree(node: Node) -> str:
    """Indented one-node-per-line rendering of an AST.

    Scalar fields sit on the node line; node-valued fields and argument
    lists indent one level deeper, with `field:` labels where the position
    alone would not say what the child is.
    """
    lines: list[str] = []

    def _is_node(value: object) -> TypeGuard[Node]:
        return is_dataclass(value) and not isinstance(value, type)

    def render(item: object, prefix: str) -> None:
        if _is_node(item):
            scalars: list[str] = []
            children: list[tuple[str, object]] = []
            for field in fields(item):
                value = getattr(item, field.name)
                if _is_node(value) or (
                    isinstance(value, tuple)
                    and bool(value)
                    and all(_is_node(v) for v in value)
                ):
                    children.append((f"{field.name}:", value))
                else:
                    scalars.append(f"{field.name}={value!r}")
            head = type(item).__name__
            if scalars:
                head += f" {' '.join(scalars)}"
            lines.append(prefix + head)
            for label, child in children:
                if isinstance(child, tuple):
                    for sub in child:
                        render(sub, prefix + "  ")
                else:
                    lines.append(prefix + f"  {label}")
                    render(child, prefix + "    ")
        else:
            lines.append(prefix + repr(item))

    render(node, "")
    return "\n".join(lines) + "\n"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dxa",
        description="DAX expression analysis: metrics, anti-pattern linting, ranking.",
    )
    parser.add_argument("--version", action="version", version=f"dxa {__version__}")
    parser.add_argument(
        "--completions",
        metavar="SHELL",
        nargs="?",
        const="",
        default=None,
        help=f"print a shell completion script and exit ({', '.join(SHELLS)})",
    )
    sub = parser.add_subparsers(dest="command")

    p_metrics = sub.add_parser("metrics", help="complexity metrics for one or more expressions")
    p_metrics.add_argument("expr", nargs="*", help="DAX expression(s), quoted")
    p_metrics.add_argument("--file", help="read one expression from this file instead")
    p_metrics.add_argument(
        "--top", type=int, metavar="N", help="keep only the N heaviest expressions (heaviest first)"
    )
    p_metrics.add_argument("--json", action="store_true", help="emit JSON")

    p_rank = sub.add_parser("rank", help="most complex measures of a model dump")
    p_rank.add_argument("model", help="path to model JSON")
    p_rank.add_argument("--top", type=int, default=10, help="how many to show")
    p_rank.add_argument("--table", help="restrict ranking to one table")
    p_rank.add_argument("--min-weight", type=int, default=None,
                        help="only measures at or above this weight")
    p_rank.add_argument("--json", action="store_true", help="emit JSON")

    p_explain = sub.add_parser("explain", help="full documentation for one rule")
    p_explain.add_argument(
        "rule",
        nargs="?",
        help="rule name as shown by dxa lint --list-rules (omit to list all rules)",
    )
    p_explain.add_argument("--json", action="store_true", help="emit JSON")

    p_lint = sub.add_parser("lint", help="anti-pattern findings for one expression")
    p_lint.add_argument("expr", nargs="?", help="DAX expression, quoted")
    p_lint.add_argument("--file", help="read the expression from this file instead")
    p_lint.add_argument("--json", action="store_true", help="emit JSON")
    p_lint.add_argument(
        "--sarif", action="store_true", help="emit SARIF 2.1.0 for CI code scanning (exit 0)"
    )
    p_lint.add_argument("--rule", action="append", metavar="NAME",
                        help="run only this rule (function name; repeatable)")
    p_lint.add_argument("--exclude-rule", action="append", metavar="NAME",
                        help="run every rule except these (repeatable; wins over --rule)")
    p_lint.add_argument("--list-rules", action="store_true", help="print the rule inventory and exit")

    p_lint_model = sub.add_parser("lint-model", help="anti-pattern findings across a model dump")
    p_lint_model.add_argument("model", help="path to model JSON (`-` for stdin)")
    p_lint_model.add_argument("--json", action="store_true", help="emit JSON")
    p_lint_model.add_argument(
        "--sarif", action="store_true", help="emit SARIF 2.1.0 per finding (exit 0)"
    )
    p_lint_model.add_argument("--table", help="restrict findings to one table")
    p_lint_model.add_argument("--rule", action="append", metavar="NAME",
                              help="run only this rule (function name; repeatable)")
    p_lint_model.add_argument("--exclude-rule", action="append", metavar="NAME",
                              help="run every rule except these (repeatable; wins over --rule)")
    p_lint_model.add_argument(
        "--summary", action="store_true", help="hit count per rule instead of per measure"
    )

    p_parse = sub.add_parser("parse", help="AST for one expression")
    p_parse.add_argument("expr", nargs="?", help="DAX expression, quoted")
    p_parse.add_argument("--file", help="read the expression from this file instead")
    p_parse.add_argument("--json", action="store_true", help="emit JSON")
    p_parse.add_argument("--tree", action="store_true", help="indented one-node-per-line tree")
    return parser


def _read_file(path: str) -> tuple[str | None, int]:
    """Read `--file PATH` (`-` is stdin), or `(None, 2)` after one line.

    Shared by the single- and multi-expression resolvers so a missing
    file or unreadable stdin fails identically for every command.
    """
    if path == "-":
        try:
            return sys.stdin.read(), 0
        except OSError as exc:
            print(f"dxa: cannot read stdin: {exc.strerror or exc}", file=sys.stderr)
            return None, 2
    try:
        return Path(path).read_text(encoding="utf-8"), 0
    except OSError as exc:
        reason = exc.strerror or str(exc)
        print(f"dxa: cannot read {path}: {reason}", file=sys.stderr)
        return None, 2


def _expression(args: argparse.Namespace) -> tuple[str | None, int]:
    """Resolve the expression from the positional or `--file`.

    Returns `(text, 0)` on success or `(None, exit_code)` after printing
    the reason to stderr, so every expression command fails the same way.
    """
    expr: str | None = getattr(args, "expr", None)
    path: str | None = getattr(args, "file", None)
    if path is not None:
        if expr is not None:
            print("dxa: give either an expression or --file, not both", file=sys.stderr)
            return None, 2
        expr, code = _read_file(path)
        if expr is None:
            return None, code
    if expr is None:
        hint = " (or --list-rules)" if args.command == "lint" else ""
        print(f"dxa: {args.command} needs an expression, --file PATH{hint}",
              file=sys.stderr)
        return None, 2
    if not expr.strip():
        source = "stdin" if path == "-" else (path or "the command line")
        print(f"dxa: {args.command} got an empty expression from {source}",
              file=sys.stderr)
        return None, 2
    return expr, 0


def _expressions(args: argparse.Namespace) -> tuple[list[str] | None, int]:
    """Resolve every expression `metrics` will analyze.

    `--file` supplies exactly one expression (a file holds one measure);
    several positionals supply several. Every positional is validated
    before anything is printed, so a multi-expression run never emits a
    partial result.
    """
    path: str | None = getattr(args, "file", None)
    given: list[str] | None = getattr(args, "expr", None)
    exprs: list[str] = list(given) if given else []
    if path is not None:
        if exprs:
            print("dxa: give either an expression or --file, not both", file=sys.stderr)
            return None, 2
        text, code = _read_file(path)
        if text is None:
            return None, code
        exprs = [text]
    if not exprs:
        print(f"dxa: {args.command} needs an expression, --file PATH",
              file=sys.stderr)
        return None, 2
    for text in exprs:
        if not text.strip():
            source = "stdin" if path == "-" else (path or "the command line")
            print(f"dxa: {args.command} got an empty expression from {source}",
                  file=sys.stderr)
            return None, 2
    return exprs, 0


def _model(path: str) -> tuple[Model | None, int]:
    """Load a model dump from a path or `-` (stdin), or exit 2 one-line.

    Missing files, broken JSON and non-object payloads are input errors,
    not crashes — every other CLI error already prints one line and
    returns 2, so the loaders must behave the same way. `-` reads the
    dump from stdin and reports errors as `stdin` rather than a path.
    """
    source = "stdin" if path == "-" else path
    try:
        if path == "-":
            data = json.loads(sys.stdin.read())
            if not isinstance(data, dict):
                raise TypeError("model dump must be a JSON object")
            return data, 0
        return load_model(path), 0
    except OSError as exc:
        reason = exc.strerror or str(exc)
        print(f"dxa: cannot read {source}: {reason}", file=sys.stderr)
        return None, 2
    except json.JSONDecodeError as exc:
        print(f"dxa: {source} is not valid JSON: {exc}", file=sys.stderr)
        return None, 2
    except TypeError as exc:
        print(f"dxa: {source} is not a model dump: {exc}", file=sys.stderr)
        return None, 2


def _only_table(model: Model, name: str) -> Model:
    """Restrict `model` to one table, matched case-insensitively.

    DAX table names are case-insensitive, so `--table sales` must find
    `Sales` — an exact-case miss would silently empty `rank` and, worse,
    make `lint-model` report "model is clean" over findings that exist.
    A table whose name is not a string never matches: typing `none`
    must not select a nameless table.
    """
    wanted = name.lower()
    return {
        "tables": [
            table for table in model.get("tables", [])
            if isinstance(table.get("name"), str) and table["name"].lower() == wanted
        ]
    }


def _rules_for(
    names: list[str] | None, excluded: list[str] | None = None
) -> tuple[list[Rule] | None, int]:
    """Resolve repeated `--rule` / `--exclude-rule` names to rules.

    Returns `(rules, 0)` — `rules` is `None` when no filter was asked
    for — or `(None, 2)` after naming every unknown rule on stderr.
    Exclusions win over selections; repeating a name runs that rule once.
    """
    if not names and not excluded:
        return None, 0
    known = {rule.__name__: rule for rule in ALL_RULES}
    unknown = [name for name in (names or []) + (excluded or []) if name not in known]
    if unknown:
        inventory = ", ".join(rule.__name__ for rule in ALL_RULES)
        print(f"dxa: unknown rule {', '.join(unknown)} — one of: {inventory}",
              file=sys.stderr)
        return None, 2
    dropped = {known[name] for name in excluded or []}
    if names:
        picked: list[Rule] = []
        for name in names:
            rule = known[name]
            if rule not in picked and rule not in dropped:
                picked.append(rule)
        return picked, 0
    return [rule for rule in ALL_RULES if rule not in dropped], 0


def main(argv: list[str] | None = None) -> int:
    """Entry point; returns a conventional exit code."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.completions is not None:
        shell = args.completions
        if shell == "":
            parser.print_usage(sys.stderr)
            print(
                f"dxa: error: --completions needs a shell — one of: "
                f"{', '.join(SHELLS)}",
                file=sys.stderr,
            )
            return 2
        if shell not in SHELLS:
            parser.print_usage(sys.stderr)
            print(
                f"dxa: error: unsupported shell {shell!r} — one of: "
                f"{', '.join(SHELLS)}",
                file=sys.stderr,
            )
            return 2
        print(completion_script(shell, parser), end="")
        return 0

    if args.command is None:
        # subparsers are optional so `--completions` can stand alone, so
        # the missing-command error is ours to reproduce — same shape
        # argparse printed when `required=True`.
        parser.print_usage(sys.stderr)
        print(
            "dxa: error: the following arguments are required: command",
            file=sys.stderr,
        )
        return 2

    if args.command == "explain":
        if args.rule is None:
            # no argument → the rule inventory, same data as --list-rules
            if getattr(args, "json", False):
                print(json.dumps(
                    [{"name": rule.__name__, "summary": rule_summary(rule)}
                     for rule in ALL_RULES]
                ))
                return 0
            for rule in ALL_RULES:
                summary = rule_summary(rule)
                print(f"{rule.__name__:36}{summary}")
            print("\nrun `dxa explain RULE` for the full documentation of one rule")
            return 0
        wanted = args.rule.strip().lower()
        match = [r for r in ALL_RULES if r.__name__.lower() == wanted]
        if not match:
            names = "\n".join(f"  {r.__name__}" for r in ALL_RULES)
            print(f"dxa: unknown rule {args.rule} — one of:\n{names}", file=sys.stderr)
            return 2
        rule = match[0]
        doc = (rule.__doc__ or "").strip()
        if getattr(args, "json", False):
            print(json.dumps({
                "name": rule.__name__,
                "summary": rule_summary(rule),
                "doc": doc,
            }))
            return 0
        print(f"{rule.__name__}\n{'-' * len(rule.__name__)}\n{doc}")
        return 0

    if args.command == "metrics":
        top = getattr(args, "top", None)
        if top is not None and top < 1:
            print("dxa: --top must be at least 1", file=sys.stderr)
            return 2
        exprs, code = _expressions(args)
        if exprs is None:
            return code
        multi = len(exprs) > 1
        if top is not None and multi:
            # stable sort: ties keep input order; the N heaviest survive
            exprs = sorted(exprs, key=weight, reverse=True)[:top]
        if getattr(args, "json", False):
            if not multi:
                single = exprs[0]
                print(json.dumps({"metrics": report(single), "weight": weight(single)}))
            else:
                results = [
                    {"expr": text, "metrics": report(text), "weight": weight(text)}
                    for text in exprs
                ]
                print(json.dumps({"results": results}))
            return 0
        for index, text in enumerate(exprs):
            if multi:
                if index:
                    print()
                print(f"expr: {' '.join(text.split())}")
            m = report(text)
            for key, value in m.items():
                print(f"{key:12}{value}")
            print(f"{'weight':12}{weight(text)}")
        return 0

    if args.command == "rank":
        model, code = _model(args.model)
        if model is None:
            return code
        only = getattr(args, "table", None)
        if only is not None:
            model = _only_table(model, only)
        rows = rank_measures(model, top=args.top, min_weight=getattr(args, "min_weight", None))
        if getattr(args, "json", False):
            print(json.dumps([{"table": t, "name": n, "weight": w} for t, n, w in rows]))
        else:
            for table, name, w in rows:
                print(f"{w:6}  {table}.{name}")
        return 0

    if args.command == "lint":
        if getattr(args, "list_rules", False):
            if getattr(args, "json", False):
                print(json.dumps(
                    [{"name": rule.__name__, "summary": rule_summary(rule)}
                     for rule in ALL_RULES]
                ))
                return 0
            for rule in ALL_RULES:
                summary = rule_summary(rule)
                print(f"{rule.__name__:36}{summary}")
            return 0
        expr, code = _expression(args)
        if expr is None:
            return code
        rules, code = _rules_for(
            getattr(args, "rule", None), getattr(args, "exclude_rule", None)
        )
        if code:
            return code
        if getattr(args, "sarif", False):
            if getattr(args, "json", False):
                print("dxa: --sarif and --json are mutually exclusive — pick one format", file=sys.stderr)
                return 2
            print(json.dumps(build_sarif(lint_findings(expr, rules), (rules if rules is not None else ALL_RULES))))
            return 0
        findings = lint_expression(expr, rules)
        if getattr(args, "json", False):
            print(json.dumps(findings))
            return 1 if findings else 0
        if findings:
            for msg in findings:
                print(f"- {msg}")
            return 1
        print("no findings")
        return 0

    if args.command == "lint-model":
        rules, code = _rules_for(
            getattr(args, "rule", None), getattr(args, "exclude_rule", None)
        )
        if code:
            return code
        model, code = _model(args.model)
        if model is None:
            return code
        only = getattr(args, "table", None)
        if only is not None:
            model = _only_table(model, only)
        if getattr(args, "sarif", False):
            if getattr(args, "json", False):
                print("dxa: --sarif and --json are mutually exclusive — pick one format", file=sys.stderr)
                return 2
            if getattr(args, "summary", False):
                print("dxa: --sarif and --summary are mutually exclusive — pick one format", file=sys.stderr)
                return 2
            print(json.dumps(build_model_sarif(
                lint_model_findings(model, rules), (rules if rules is not None else ALL_RULES), args.model
            )))
            return 0
        if getattr(args, "summary", False):
            counts = lint_model_summary(model, rules)
            if getattr(args, "json", False):
                print(json.dumps(counts))
                return 1 if counts else 0
            if not counts:
                print("model is clean")
                return 0
            for rule_name_, hits in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
                print(f"{hits:5}  {rule_name_}")
            return 1
        found = lint_model(model, rules)
        if not found:
            print("model is clean")
            return 0
        if getattr(args, "json", False):
            print(json.dumps(found))
        else:
            for key, msgs in found.items():
                print(f"{key}:")
                for msg in msgs:
                    print(f"  - {msg}")
        return 1

    if args.command == "parse":
        if getattr(args, "json", False) and getattr(args, "tree", False):
            print("dxa: --json and --tree are mutually exclusive — pick one format",
                  file=sys.stderr)
            return 2
        expr, code = _expression(args)
        if expr is None:
            return code
        try:
            tree = parse(expr)
        except ParseError as err:
            print(f"dxa: parse error: {err}", file=sys.stderr)
            return 2
        if getattr(args, "json", False):
            print(json.dumps(asdict(tree), indent=2))
        elif getattr(args, "tree", False):
            print(format_tree(tree), end="")
        else:
            print(tree)
        return 0

    return 2  # unreachable: argparse requires a subcommand


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
