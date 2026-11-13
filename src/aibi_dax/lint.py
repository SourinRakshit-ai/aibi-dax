"""Lint DAX expressions across a model using every anti-pattern rule."""

from __future__ import annotations

from .antipattern import ALL_RULES, Rule
from .lexer import strip_comments
from .model_io import Model


def lint_expression(expr: str, rules: list[Rule] | None = None) -> list[str]:
    """All findings a single expression trips, human-readable.

    Comments are blanked before the rules see the text — `-- note about
    CALCULATE` must not trip the calculate_inside_iterator fallback.
    """
    return [msg for rule in (rules or ALL_RULES) for msg in [rule(strip_comments(expr))] if msg]


def lint_model(model: Model, rules: list[Rule] | None = None) -> dict[str, list[str]]:
    """Map measure keys ("table.name") to their findings; empty when clean."""
    out: dict[str, list[str]] = {}
    for table in model.get("tables", []):
        table_name = str(table.get("name", "?"))
        for measure in table.get("measures", []):
            key = f"{table_name}.{measure.get('name', '?')}"
            findings = lint_expression(str(measure.get("expression", "")), rules)
            if findings:
                out[key] = findings
    return out


def lint_model_summary(model: Model, rules: list[Rule] | None = None) -> dict[str, int]:
    """How many measures each rule fires on, for a model-wide cleanup plan.

    Rules that fire on nothing are omitted, so the result reads as a
    priority list rather than a rule inventory. Comment text is blanked
    before the rules run, exactly as in `lint_expression`.
    """
    counts: dict[str, int] = {}
    for table in model.get("tables", []):
        for measure in table.get("measures", []):
            expr = strip_comments(str(measure.get("expression", "")))
            for rule in rules or ALL_RULES:
                if rule(expr):
                    counts[rule.__name__] = counts.get(rule.__name__, 0) + 1
    return counts
