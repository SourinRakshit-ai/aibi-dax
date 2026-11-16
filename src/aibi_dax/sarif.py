"""SARIF 2.1.0 documents for CI code scanning."""

from __future__ import annotations

from typing import Any

from . import __version__
from .antipattern import Rule, rule_summary

REPO_URL = "https://github.com/SourinRakshit-ai/aibi-dax"


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
                "tool": {
                    "driver": {
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
                },
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
