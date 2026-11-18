"""SARIF 2.1.0 documents for CI code scanning."""

from __future__ import annotations

from typing import Any

from . import __version__
from .antipattern import Rule, rule_summary

REPO_URL = "https://github.com/SourinRakshit-ai/aibi-dax"


def _driver(rules: list[Rule]) -> dict[str, Any]:
    return {
        "name": "aibi-dax",
        "version": __version__,
        "informationUri": REPO_URL,
        "rules": [
            {
                "id": rule.__name__,
                "shortDescription": {"text": rule_summary(rule) or rule.__name__},
            }
            for rule in rules
        ],
    }


def build_model_sarif(
    findings: list[tuple[str, str, str]], rules: list[Rule], path_hint: str
) -> dict[str, Any]:
    """One-run SARIF 2.1.0 document for `dxa lint-model --sarif`.

    Each finding triple is (measure_key, rule, message). The
    `locations[].physicalLocation.artifactLocation.uri` for a result
    is the model path as given on the command line, with a JSON
    Pointer fragment (`#/tables/<table>/measures/<name>`) into the
    measure; names are RFC 6901 escaped (`~` → `~0`, `/` → `~1`).
    When the model comes from stdin the uri is `-` to match the CLI.
    """
    results: list[dict[str, Any]] = []
    for key, rule_name, message in findings:
        table, _sep, measure = key.partition(".")
        fragment = f"#/tables/{_escape_pointer(table)}/measures/{_escape_pointer(measure)}"
        results.append(
            {
                "ruleId": rule_name,
                "level": "warning",
                "message": {"text": message},
                "locations": [
                    {
                        "physicalLocation": {
                            "artifactLocation": {"uri": f"{path_hint}{fragment}"}
                        }
                    }
                ],
            }
        )
    return {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [{"tool": {"driver": _driver(rules)}, "results": results}],
    }


def _escape_pointer(part: str) -> str:
    return part.replace("~", "~0").replace("/", "~1")


def build_sarif(findings: list[tuple[str, str]], rules: list[Rule]) -> dict[str, Any]:
    """One-run SARIF 2.1.0 document for `dxa lint --sarif`.

    `rules` is the inventory the run was linted against (so a
    `--rule`-filtered document describes only those rules). Findings
    arrive as (rule, message) pairs from `lint_findings`.
    """
    return {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {"driver": _driver(rules)},
                "results": [
                    {
                        "ruleId": rule_name,
                        "level": "warning",
                        "message": {"text": message},
                    }
                    for rule_name, message in findings
                ],
            }
        ],
    }
