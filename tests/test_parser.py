"""Tests for the recursive-descent DAX parser (issue #1 groundwork)."""

from __future__ import annotations

import pytest

from aibi_dax.parser import (
    Binary,
    Call,
    ColumnRef,
    Ident,
    Literal,
    ParseError,
    TableRef,
    Unary,
    Var,
    parse,
)


def test_precedence_multiplication_binds_tighter() -> None:
    tree = parse("1 + 2 * 3")
    assert tree == Binary(op="+", left=Literal("1"),
                          right=Binary(op="*", left=Literal("2"), right=Literal("3")))


def test_left_associative_comparison_chain() -> None:
    tree = parse("a = b = c")
    middle = Binary(op="=", left=Ident("a"), right=Ident("b"))
    assert tree == Binary(op="=", left=middle, right=Ident("c"))


def test_iterator_over_table_measures_calc() -> None:
    """The canonical iterator shape: SUMX('Sales', CALCULATE([Amount]))."""
    tree = parse("SUMX('Sales', CALCULATE([Amount]))")
    assert isinstance(tree, Call)
    assert tree.name == "SUMX"
    assert tree.args == (
        TableRef(name="'Sales'"),
        Call(name="CALCULATE", args=(ColumnRef(name="Amount"),)),
    )


def test_table_arg_alone_is_a_table_ref() -> None:
    assert parse("'Sales'") == TableRef(name="'Sales'")


def test_nullary_call() -> None:
    assert parse("TODAY()") == Call(name="TODAY", args=())


def test_unary_minus_precedence() -> None:
    assert parse("-3 + 5") == Binary(op="+", left=Unary(op="-", operand=Literal("3")),
                                     right=Literal("5"))


def test_string_literal_is_literal() -> None:
    assert parse('"Q"') == Literal(text='"Q"')


def test_parenthesized_expression_overrides() -> None:
    assert parse("(1 + 2) * 3") == Binary(
        op="*", left=Binary(op="+", left=Literal("1"), right=Literal("2")),
        right=Literal("3"),
    )


def test_parse_error_on_dangling_tokens() -> None:
    with pytest.raises(ParseError):
        parse("1 +")


def test_parse_error_on_unclosed_call() -> None:
    with pytest.raises(ParseError):
        parse("SUM(")


def test_amp_binds_tighter_than_plus() -> None:
    tree = parse("1 + [A] & \"x\"")
    assert isinstance(tree, Binary) and tree.op == "+"
    amp = tree.right
    assert isinstance(amp, Binary) and amp.op == "&"


def test_var_block_parses() -> None:
    tree = parse("VAR k = [x] + 1 RETURN k")
    assert tree == Var(
        name="k",
        value=Binary(op="+", left=ColumnRef("x"), right=Literal("1")),
        body=Ident("k"),
    )


def test_chained_var_blocks_nest() -> None:
    tree = parse("VAR a = 1 VAR b = 2 RETURN a + b")
    assert tree == Var(
        name="a",
        value=Literal("1"),
        body=Var(
            name="b",
            value=Literal("2"),
            body=Binary(op="+", left=Ident("a"), right=Ident("b")),
        ),
    )


def test_var_without_return_is_an_error() -> None:
    with pytest.raises(ParseError):
        parse("VAR k = 1")
    with pytest.raises(ParseError):
        parse("VAR k [x]")


def test_iterator_inside_var_is_seen_by_rules() -> None:
    """The lint walkers must descend Var blocks (regression for rule 12)."""
    from aibi_dax.antipattern import nested_iterators

    assert nested_iterators("VAR s = SUMX('S', AVERAGEX('S', [x])) RETURN s") is not None
    assert nested_iterators("VAR s = SUMX('S', [x]) RETURN s") is None
