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
