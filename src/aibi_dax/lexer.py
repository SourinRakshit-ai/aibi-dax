"""Tokenize DAX expressions into stable units for analysis."""

from __future__ import annotations

import re
from dataclasses import dataclass

_TOKEN_RE = re.compile(
    r'"[^"]*"'  # double-quoted string literal
    r"|'[^']*'"  # quoted table name
    r"|\b[A-Za-z_][A-Za-z0-9_.]*\b"  # word (identifier / function / keyword)
    r"|\[\s*[^]]*?\s*\]"  # column reference [Column Name]
    r"|\d+(?:\.\d+)?"  # numeric literal
    r"|\S",  # any single non-space symbol
    re.VERBOSE,
)


@dataclass(frozen=True)
class Token:
    """One lexical unit: a string literal, quoted table, bracketed column, word or symbol."""

    kind: str  # "string" | "table" | "column" | "word" | "symbol"
    value: str


def tokenize(expr: str) -> list[Token]:
    """Split a DAX expression into tokens, dropping whitespace."""
    toks: list[Token] = []
    for match in _TOKEN_RE.finditer(expr):
        text = match.group(0)
        if text.isspace() or (len(text) == 1 and not text.isprintable()):
            continue
        if text[:1] == '"':
            kind = "string"
        elif text[:1] == "'":
            kind = "table"
        elif text[:1] == "[":
            kind = "column"
        elif text[:1].isalpha() or text[:1] == "_":
            kind = "word"
        elif text[:1].isdigit():
            kind = "number"
        else:
            kind = "symbol"
        toks.append(Token(kind=kind, value=text))
    return toks
