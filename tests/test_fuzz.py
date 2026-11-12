"""Fuzz: parse() and lint_expression() never raise an unexpected exception.

The parser's contract with the rule engine is narrow: either a tree comes
back, or ParseError — every rule relies on that. Seeded random token soup
keeps the property checked against inputs no hand-written test would think
to try. Same seed always builds the same soup, so failures reproduce.
"""

from __future__ import annotations

import random

import pytest

from aibi_dax.lint import lint_expression
from aibi_dax.parser import ParseError, parse

TOKENS = [
    "SUM", "SUMX", "CALCULATE", "IF", "VAR", "RETURN", "BLANK",
    "(", ")", ",", "+", "-", "*", "/", "[x]", "'S'", '"lit"', "1", "0.5",
]


@pytest.mark.parametrize("seed", range(60))
def test_parser_never_leaks_internal_errors(seed: int) -> None:
    rng = random.Random(seed)
    for _ in range(40):
        expr = " ".join(rng.choice(TOKENS) for _ in range(rng.randint(1, 30)))
        try:
            tree = parse(expr)
        except ParseError:
            continue
        assert tree is not None


@pytest.mark.parametrize("seed", range(20))
def test_lint_never_leaks_internal_errors(seed: int) -> None:
    rng = random.Random(seed)
    for _ in range(50):
        expr = " ".join(rng.choice(TOKENS) for _ in range(rng.randint(1, 30)))
        findings = lint_expression(expr)  # noqa: F841 — must not raise
