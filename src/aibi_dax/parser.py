"""Recursive-descent parser: DAX expression text to a small AST.

Issue #1 groundwork — the tokenizer sees calls as flat token streams; this
module reduces the same tokens to a tree so rules and tools can reason about
argument positions and nesting instead of regex fragments.

Precedence, loosest binding first: `||`, `&&`, comparison (left-assoc), `+ -`,
`&`, `* /`, unary `- +`, primary (calls, refs, parenthesization). The parser is
permissive: it accepts a syntactic superset of real DAX (e.g. `%` symbols) so
lint never crashes on odd-but-parseable text; genuinely unreducible sequences
raise ParseError.
"""

from __future__ import annotations

from dataclasses import dataclass

from .lexer import Token, tokenize


class ParseError(ValueError):
    """The token sequence cannot be reduced to one expression."""


@dataclass(frozen=True)
class Literal:
    """A number (`3`, `0.1`) or string literal (`\"Q\"`)."""

    text: str


@dataclass(frozen=True)
class ColumnRef:
    """`[Column Name]`, brackets stripped."""

    name: str


@dataclass(frozen=True)
class TableRef:
    """A quoted table argument, quote marks preserved (`'Sales'`)."""

    name: str


@dataclass(frozen=True)
class Ident:
    """A bare identifier that is not a call or a column."""

    name: str


@dataclass(frozen=True)
class Call:
    """`NAME(arg1, ..., argN)` with parsed arguments."""

    name: str
    args: tuple[Node, ...]


@dataclass(frozen=True)
class Binary:
    """An infix operator application."""

    op: str
    left: Node
    right: Node


@dataclass(frozen=True)
class Unary:
    """A prefix operator application (`-x`, `+x`, `!`)."""

    op: str
    operand: Node


Node = Literal | ColumnRef | TableRef | Ident | Call | Binary | Unary

# Precedence ladder: index binds looser -> tighter.
_LEVELS: tuple[tuple[str, ...], ...] = (
    ("||",),
    ("&&",),
    ("=", "<>", "<", ">", "<=", ">="),
    ("+", "-"),
    ("&",),
    ("*", "/", "%"),
)


class _Parser:
    def __init__(self, tokens: list[Token]) -> None:
        self._toks = tokens
        self._i = 0

    def _peek(self) -> Token | None:
        if self._i < len(self._toks):
            return self._toks[self._i]
        return None

    def _next(self) -> Token:
        tok = self._peek()
        if tok is None:
            raise ParseError("unexpected end of expression")
        self._i += 1
        return tok

    def _error(self, why: str) -> ParseError:
        tok = self._peek()
        where = "end of expression" if tok is None else f"near {tok.value!r}"
        return ParseError(f"{why} ({where}, token {self._i})")

    def parse(self) -> Node:
        node = self._expr()
        if self._peek() is not None:
            raise self._error("dangling tokens after expression")
        return node

    def _expr(self, level: int = 0) -> Node:
        if level == len(_LEVELS):
            return self._unary()
        left = self._expr(level + 1)
        while (tok := self._peek()) is not None and tok.value in _LEVELS[level]:
            op = self._next().value
            right = self._expr(level + 1)
            left = Binary(op=op, left=left, right=right)
        return left

    def _unary(self) -> Node:
        tok = self._peek()
        if tok is not None and tok.kind == "symbol" and tok.value in ("-", "+", "!"):
            return Unary(op=self._next().value, operand=self._unary())
        return self._primary()

    def _primary(self) -> Node:
        tok = self._next()
        if tok.kind == "number":
            return Literal(text=tok.value)
        if tok.kind == "string":
            return Literal(text=tok.value)
        if tok.kind == "column":
            return ColumnRef(name=tok.value.strip("[] \t"))
        if tok.kind == "table":
            return TableRef(name=tok.value)
        if tok.kind == "word":
            nxt = self._peek()
            if nxt is not None and nxt.value == "(":
                return self._call(name=tok.value)
            return Ident(name=tok.value)
        if tok.kind == "symbol" and tok.value == "(":
            inner = self._expr()
            closing = self._peek()
            if closing is not None and closing.value == ")":
                self._next()
                return inner
            raise self._error("expected ')'")
        # Number, string, column, table, word or paren-expr all reduce above;
        # anything else cannot start an expression.
        raise self._error("expected number, string, column, word or '('")

    def _call(self, name: str) -> Node:
        self._next()  # consume the '(' we peeked
        args: list[Node] = []
        if self._peek() is not None and self._peek().value == ")":  # type: ignore[union-attr]
            self._next()
            return Call(name=name, args=())
        while True:
            args.append(self._expr())
            sep = self._peek()
            if sep is None:
                raise self._error(f"unterminated arguments of {name}(…")
            if sep.value == ",":
                self._next()
                continue
            if sep.value == ")":
                self._next()
                return Call(name=name, args=tuple(args))
            raise self._error(f"expected ',' or ')' inside {name}(…")


def parse(expr: str) -> Node:
    """Reduce a DAX expression string to one AST node tree."""
    return _Parser(tokenize(expr)).parse()
