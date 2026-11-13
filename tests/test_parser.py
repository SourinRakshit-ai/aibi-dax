"""Tests for the recursive-descent DAX parser (issue #1 groundwork)."""

from __future__ import annotations

import pytest

from aibi_dax.complexity import weight
from aibi_dax.parser import (
    Binary,
    Call,
    ColumnRef,
    Ident,
    List,
    Literal,
    ParseError,
    QualifiedColumn,
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


def test_fully_qualified_column_reference() -> None:
    """'Table'[Column] reduces to one QualifiedColumn node."""
    tree = parse("SUM('Sales'[Amount])")
    assert tree == Call(name="SUM", args=(QualifiedColumn(table="'Sales'", name="Amount"),))
    assert parse("'Sales'[Amount] * 2") == Binary(
        op="*", left=QualifiedColumn(table="'Sales'", name="Amount"), right=Literal("2")
    )


def test_column_bracket_escape() -> None:
    """A literal ] inside a column name is written ]] (DAX escaping)."""
    assert parse("[Profit %]]]") == ColumnRef(name="Profit %]")
    assert parse("SUM('S'[Profit %]]])") == Call(
        name="SUM", args=(QualifiedColumn(table="'S'", name="Profit %]"),)
    )
    # a doubled escape is two literal brackets
    assert parse("[A]]]]]") == ColumnRef(name="A]]")


def test_line_comments_are_stripped() -> None:
    """// and -- comments never reach the token stream."""
    assert parse("[a] + [b] -- trailing note") == parse("[a] + [b]")
    assert parse("SUM(1) // total") == parse("SUM(1)")
    with pytest.raises(ParseError):
        parse("// only a comment")
    with pytest.raises(ParseError):
        parse("")


def test_block_comments_are_stripped() -> None:
    assert parse("/* header */ [a]") == ColumnRef(name="a")
    assert parse("/* multi\nline\n*/ [a] + 1") == parse("[a] + 1")
    assert parse("[a] /* mid */ + /* mid */ 1") == parse("[a] + 1")


def test_comment_lookalikes_inside_strings_survive() -> None:
    """//, -- and /* inside string literals and column names are text."""
    assert parse('"// not a comment"') == Literal('"// not a comment"')
    assert parse("'T // x'[c -- d]") == QualifiedColumn(table="'T // x'", name="c -- d")
    assert weight('"a // b"') > 0


def test_commented_measure_lints_like_uncommented() -> None:
    """A comment mentioning CALCULATE must not trip the AST fallback."""
    from aibi_dax.lint import lint_expression

    assert lint_expression("[a] + 1 -- consider CALCULATE(x)") == []
    assert lint_expression("SUM(1) /* /5 */") == []
    # the commented form of a dirty expression still trips the rule
    assert lint_expression("SUMX('S', CALCULATE([x])) // row context") != []


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


def test_parse_error_carries_source_offset() -> None:
    """The error points at the character offset, not just a token index."""
    with pytest.raises(ParseError) as exc:
        parse("[a] [b]")
    assert "near '[b]' at char 4" in str(exc.value)
    with pytest.raises(ParseError) as exc2:
        parse("SUM('S' [x]")
    assert "end of expression, token 4" in str(exc2.value)


def test_two_char_operators_lex_as_single_symbols() -> None:
    """>= <= <> && || were previously split into single-char tokens, so the
    precedence ladder could never match them (`1 >= -1` failed to parse)."""
    assert parse("1 >= -1") == Binary(
        op=">=", left=Literal("1"), right=Unary(op="-", operand=Literal("1"))
    )
    assert parse("[a] <= [b]").op == "<="  # type: ignore[union-attr]
    assert parse("[a] <> [b]").op == "<>"  # type: ignore[union-attr]
    assert parse("[a] && [b]").op == "&&"  # type: ignore[union-attr]
    assert parse("TRUE() || FALSE()").op == "||"  # type: ignore[union-attr]


def test_iterator_inside_var_is_seen_by_rules() -> None:
    """The lint walkers must descend Var blocks (regression for rule 12)."""
    from aibi_dax.antipattern import nested_iterators

    assert nested_iterators("VAR s = SUMX('S', AVERAGEX('S', [x])) RETURN s") is not None
    assert nested_iterators("VAR s = SUMX('S', [x]) RETURN s") is None


def test_in_list_literal_parses() -> None:
    """[k] IN {…} is a comparison-level binary with a List right side."""
    assert parse("[k] IN {1, 2}") == Binary(
        op="IN",
        left=ColumnRef(name="k"),
        right=List(items=(Literal("1"), Literal("2"))),
    )
    assert parse("'STATUS'[Name] IN {\"Won\", \"Lost\"}") == Binary(
        op="IN",
        left=QualifiedColumn(table="'STATUS'", name="Name"),
        right=List(items=(Literal('"Won"'), Literal('"Lost"'))),
    )
    # keyword case does not matter, the node normalizes to upper-case IN
    assert parse("[k] in {1}") == parse("[k] IN {1}")


def test_list_items_hold_full_expressions() -> None:
    tree = parse("[a] IN {[b] + 1, SUM({1, 2})}")
    assert isinstance(tree, Binary) and isinstance(tree.right, List)
    inner, nested = tree.right.items
    assert inner == Binary(op="+", left=ColumnRef(name="b"), right=Literal("1"))
    assert nested == Call(name="SUM", args=(List(items=(Literal("1"), Literal("2"))),))
    assert parse("FILTER(T, [k] IN {1,2})") == Call(
        name="FILTER",
        args=(Ident(name="T"), Binary(
            op="IN", left=ColumnRef(name="k"),
            right=List(items=(Literal("1"), Literal("2"))),
        )),
    )


def test_empty_list_is_allowed_but_empty_items_are_not() -> None:
    assert parse("{}") == List(items=())
    for bad in ("[a] IN {1,}", "[a] IN {,}", "[a] IN {1, ,2}", "[a] IN {1"):
        with pytest.raises(ParseError):
            parse(bad)


def test_rules_see_calls_inside_lists() -> None:
    """AST walkers descend List items (rule 12 nested_iterators regression)."""
    from aibi_dax.lint import lint_expression

    assert lint_expression("[x] IN {SUMX('S', AVERAGEX('S', [y]))}") != []
    assert lint_expression("[x] IN {1, 2}") == []
