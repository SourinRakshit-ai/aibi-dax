"""Command-line interface for aibi-dax (`dxa`)."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, fields, is_dataclass
from typing import TypeGuard

from . import __version__
from .antipattern import ALL_RULES
from .complexity import rank_measures, report, weight
from .lint import lint_expression, lint_model
from .model_io import load_model
from .parser import Node, ParseError, parse


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
    sub = parser.add_subparsers(dest="command", required=True)

    p_metrics = sub.add_parser("metrics", help="complexity metrics for one expression")
    p_metrics.add_argument("expr", help="DAX expression, quoted")
    p_metrics.add_argument("--json", action="store_true", help="emit JSON")

    p_rank = sub.add_parser("rank", help="most complex measures of a model dump")
    p_rank.add_argument("model", help="path to model JSON")
    p_rank.add_argument("--top", type=int, default=10, help="how many to show")
    p_rank.add_argument("--table", help="restrict ranking to one table")
    p_rank.add_argument("--json", action="store_true", help="emit JSON")

    p_lint = sub.add_parser("lint", help="anti-pattern findings for one expression")
    p_lint.add_argument("expr", nargs="?", help="DAX expression, quoted")
    p_lint.add_argument("--json", action="store_true", help="emit JSON")
    p_lint.add_argument("--rule", help="run only this rule (function name)")
    p_lint.add_argument("--list-rules", action="store_true", help="print the rule inventory and exit")

    p_lint_model = sub.add_parser("lint-model", help="anti-pattern findings across a model dump")
    p_lint_model.add_argument("model", help="path to model JSON")
    p_lint_model.add_argument("--json", action="store_true", help="emit JSON")
    p_lint_model.add_argument("--table", help="restrict findings to one table")
    p_lint_model.add_argument("--rule", help="run only this rule (function name)")

    p_parse = sub.add_parser("parse", help="AST for one expression")
    p_parse.add_argument("expr", help="DAX expression, quoted")
    p_parse.add_argument("--json", action="store_true", help="emit JSON")
    p_parse.add_argument("--tree", action="store_true", help="indented one-node-per-line tree")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point; returns a conventional exit code."""
    args = _build_parser().parse_args(argv)

    if args.command == "metrics":
        m = report(args.expr)
        if getattr(args, "json", False):
            print(json.dumps({"metrics": m, "weight": weight(args.expr)}))
        else:
            for key, value in m.items():
                print(f"{key:12}{value}")
            print(f"{'weight':12}{weight(args.expr)}")
        return 0

    if args.command == "rank":
        model = load_model(args.model)
        only = getattr(args, "table", None)
        if only is not None:
            model = {"tables": [t for t in model.get("tables", []) if t.get("name") == only]}
        rows = rank_measures(model, top=args.top)
        if getattr(args, "json", False):
            print(json.dumps([{"table": t, "name": n, "weight": w} for t, n, w in rows]))
        else:
            for table, name, w in rows:
                print(f"{w:6}  {table}.{name}")
        return 0

    if args.command == "lint":
        if getattr(args, "list_rules", False):
            for rule in ALL_RULES:
                text = " ".join((rule.__doc__ or "").strip().splitlines())
                sentence = text.partition(". ")[0]
                summary = sentence[:97] + "…" if len(sentence) > 98 else sentence
                print(f"{rule.__name__:26}{summary}")
            return 0
        if args.expr is None:
            print("dxa: lint needs an expression (or --list-rules)", file=sys.stderr)
            return 2
        rules = None
        rule_name = getattr(args, "rule", None)
        if rule_name is not None:
            rules = [r for r in ALL_RULES if r.__name__ == rule_name]
            if not rules:
                names = ", ".join(r.__name__ for r in ALL_RULES)
                print(f"dxa: unknown rule {rule_name} — one of: {names}", file=sys.stderr)
                return 2
        findings = lint_expression(args.expr, rules)
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
        rules = None
        rule_name = getattr(args, "rule", None)
        if rule_name is not None:
            rules = [r for r in ALL_RULES if r.__name__ == rule_name]
            if not rules:
                names = ", ".join(r.__name__ for r in ALL_RULES)
                print(f"dxa: unknown rule {rule_name} — one of: {names}", file=sys.stderr)
                return 2
        found = lint_model(load_model(args.model), rules)
        only = getattr(args, "table", None)
        if only is not None:
            found = {k: v for k, v in found.items() if k.split(".", 1)[0] == only}
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
        try:
            tree = parse(args.expr)
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
