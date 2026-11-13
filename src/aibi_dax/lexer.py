"""Tokenize DAX expressions into stable units for analysis."""

from __future__ import annotations

import re
from dataclasses import dataclass

_STRING_RE = r'"(?:[^"]|"")*"'  # a doubled "" stays inside the literal
_TABLE_RE = r"'(?:[^']|'')*'"  # a doubled '' stays inside the table name
_COLUMN_RE = r"\[[^\]]*(?:\]\][^\]]*)*\]"  # a doubled ]] stays inside the column

_TOKEN_RE = re.compile(
    _STRING_RE
    + "|" + _TABLE_RE
    + "|" + r"\b[A-Za-z_][A-Za-z0-9_.]*\b"  # word (identifier / function / keyword)
    + "|" + _COLUMN_RE  # column ref; a literal ] inside is escaped ]]
    + "|" + r"\d+(?:\.\d+)?"  # numeric literal
    + "|" + r">=|<=|<>|&&|\|\|"  # two-char operators (matched before single symbols)
    + "|" + r"\S",  # any single non-space symbol
    re.VERBOSE,
)


@dataclass(frozen=True)
class Token:
    """One lexical unit: a string literal, quoted table, bracketed column, word or symbol."""

    kind: str  # "string" | "table" | "column" | "word" | "symbol"
    value: str
    pos: int  # character offset in the source expression


_COMMENT_RE = re.compile(
    _STRING_RE + "|" + _TABLE_RE + "|" + _COLUMN_RE  # keep literals intact
    + "|//[^\n]*"  # DAX line comment
    + "|--[^\n]*"  # DAX line comment (double-dash; single - is subtraction)
    + r"|/\*.*?\*/",  # DAX block comment
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


_DELIMS = {
    '"': ('"', "string"),
    "'": ("'", "quoted table name"),
    "[": ("]", "bracketed column"),
}


def unterminated(expr: str) -> str | None:
    """Describe the first unterminated quote or bracket in `expr`, if any.

    DAX escapes a delimiter by doubling it (`\"a\"\"b\"`, `'T''x'`,
    `[A]]]`), so a doubled delimiter stays inside the literal. Comments
    are stripped first, so punctuation inside them cannot confuse the
    scan. Returns None for well-formed text.
    """
    code = strip_comments(expr)
    i = 0
    n = len(code)
    while i < n:
        ch = code[i]
        if ch in _DELIMS:
            close, kind = _DELIMS[ch]
            start = i
            i += 1
            while i < n:
                if code[i] == close:
                    if i + 1 < n and code[i + 1] == close:  # doubled delimiter
                        i += 2
                        continue
                    i += 1
                    break
                i += 1
            else:
                return f"unterminated {kind} starting at char {start}"
        else:
            i += 1
    return None


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
