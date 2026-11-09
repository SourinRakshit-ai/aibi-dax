"""Command-line interface for aibi-dax (`dxa`)."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict

from . import __version__
from .complexity import rank_measures, report, weight
from .lint import lint_expression, lint_model
from .model_io import load_model
from .parser import ParseError, parse


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
    p_rank.add_argument("--json", action="store_true", help="emit JSON")

    p_lint = sub.add_parser("lint", help="anti-pattern findings for one expression")
    p_lint.add_argument("expr", help="DAX expression, quoted")

    p_lint_model = sub.add_parser("lint-model", help="anti-pattern findings across a model dump")
    p_lint_model.add_argument("model", help="path to model JSON")
    p_lint_model.add_argument("--json", action="store_true", help="emit JSON")

    p_parse = sub.add_parser("parse", help="AST for one expression")
    p_parse.add_argument("expr", help="DAX expression, quoted")
    p_parse.add_argument("--json", action="store_true", help="emit JSON")
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
        rows = rank_measures(load_model(args.model), top=args.top)
        if getattr(args, "json", False):
            print(json.dumps([{"table": t, "name": n, "weight": w} for t, n, w in rows]))
        else:
            for table, name, w in rows:
                print(f"{w:6}  {table}.{name}")
        return 0

    if args.command == "lint":
        findings = lint_expression(args.expr)
        if findings:
            for msg in findings:
                print(f"- {msg}")
            return 1
        print("no findings")
        return 0

    if args.command == "lint-model":
        found = lint_model(load_model(args.model))
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
        else:
            print(tree)
        return 0

    return 2  # unreachable: argparse requires a subcommand


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
