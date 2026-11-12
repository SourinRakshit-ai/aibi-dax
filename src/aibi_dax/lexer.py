"""Tokenize DAX expressions into stable units for analysis."""

from __future__ import annotations

import re
from dataclasses import dataclass

_TOKEN_RE = re.compile(
    r'"[^"]*"'  # double-quoted string literal
    r"|'[^']*'"  # quoted table name
    r"|\b[A-Za-z_][A-Za-z0-9_.]*\b"  # word (identifier / function / keyword)
    r"|\[[^\]]*(?:\]\][^\]]*)*\]"  # column ref; a literal ] inside is escaped ]]
    r"|\d+(?:\.\d+)?"  # numeric literal
    r"|>=|<=|<>|&&|\|\|"  # two-char operators (matched before single symbols)
    r"|\S",  # any single non-space symbol
    re.VERBOSE,
)


@dataclass(frozen=True)
class Token:
    """One lexical unit: a string literal, quoted table, bracketed column, word or symbol."""

    kind: str  # "string" | "table" | "column" | "word" | "symbol"
    value: str
    pos: int  # character offset in the source expression


_COMMENT_RE = re.compile(
    r'"[^"]*"'  # keep string literals intact — "//" inside them is text
    r"|'[^']*'"  # keep quoted table names intact
    r"|\[[^\]]*(?:\]\][^\]]*)*\]"  # keep bracketed columns (may contain //, --)
    r"|//[^\n]*"  # DAX line comment
    r"|--[^\n]*"  # DAX line comment (double-dash; single - is subtraction)
    r"|/\*.*?\*/",  # DAX block comment
    re.DOTALL,
)


def strip_comments(expr: str) -> str:
    """Blank out DAX comments, preserving length and newlines.

    Line (`//`, `--`) and block (`/* … */`) comments are replaced by
    spaces of exactly their length, so character offsets stay valid for
    the parser's `at char N` messages and quoted strings, table names,
    and bracketed columns that merely look like comments are untouched.
    """
    def _keep_or_blank(match: re.Match[str]) -> str:
        head = match.group(0)[:1]
        if head in ('"', "'", "["):
            return match.group(0)
        return " " * len(match.group(0))

    return _COMMENT_RE.sub(_keep_or_blank, expr)


def tokenize(expr: str) -> list[Token]:
    """Split a DAX expression into tokens, dropping whitespace and comments."""
    toks: list[Token] = []
    for match in _TOKEN_RE.finditer(strip_comments(expr)):
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
        toks.append(Token(kind=kind, value=text, pos=match.start()))
    return toks
