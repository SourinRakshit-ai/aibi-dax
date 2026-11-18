"""Lint DAX expressions across a model using every anti-pattern rule."""

from __future__ import annotations

from .antipattern import ALL_RULES, Rule
from .lexer import strip_comments
from .model_io import Model


def lint_findings(expr: str, rules: list[Rule] | None = None) -> list[tuple[str, str]]:
    """All findings a single expression trips, as (rule, message) pairs.

    Comments are blanked before the rules see the text — `-- note about
    CALCULATE` must not trip the calculate_inside_iterator fallback.
    Machine consumers (SARIF) need the rule attribution, so this is
    the shared entry point and `lint_expression` is a thin projection.
    """
    stripped = strip_comments(expr)
    out: list[tuple[str, str]] = []
    for rule in (rules if rules is not None else ALL_RULES):
        msg = rule(stripped)
        if msg:
            out.append((rule.__name__, msg))
    return out


def lint_expression(expr: str, rules: list[Rule] | None = None) -> list[str]:
    """All findings a single expression trips, human-readable."""
    return [msg for _, msg in lint_findings(expr, rules)]


def lint_model_findings(
    model: Model, rules: list[Rule] | None = None
) -> list[tuple[str, str, str]]:
    """Per-measure findings as (measure_key, rule, message) triples.

    `measure_key` is "table.name", like `lint_model` reports. Comment
    text is blanked before the rules run, exactly as `lint_expression`.
    Shared by `lint_model` (human output) and machine consumers like
    `--sarif`, so both describe the same run.
    """
    out: list[tuple[str, str, str]] = []
    for table in model.get("tables", []):
        table_name = str(table.get("name", "?"))
        for measure in table.get("measures", []):
            key = f"{table_name}.{measure.get('name', '?')}"
            pairs = lint_findings(str(measure.get("expression", "")), rules)
            out.extend((key, rule_name, message) for rule_name, message in pairs)
    return out


def lint_model(model: Model, rules: list[Rule] | None = None) -> dict[str, list[str]]:
    """Map measure keys ("table.name") to their findings; empty when clean."""
    out: dict[str, list[str]] = {}
    for key, _, message in lint_model_findings(model, rules):
        out.setdefault(key, []).append(message)
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
            for rule in (rules if rules is not None else ALL_RULES):
                if rule(expr):
                    counts[rule.__name__] = counts.get(rule.__name__, 0) + 1
    return counts
