"""Tests for the DAX tokenizer."""

import pytest

from aibi_dax.lexer import tokenize


def test_tokenize_functions_and_strings():
    toks = tokenize('CONCATENATEX(Sales, "Q" & [Month], "-")')
    kinds = [t.kind for t in toks]
    values = [t.value for t in toks]
    assert "CONCATENATEX" in values and "Sales" in values
    assert kinds.count("word") == 2
    assert '"-"' in values
    assert "CONCATENATEX" in values


def test_tokenize_table_and_column_refs():
    toks = tokenize("'Sales Table'[Order Qty]")
    assert any(t.kind == "table" and t.value == "'Sales Table'" for t in toks)
    assert any(t.kind == "column" for t in toks)


def test_tokenize_paren_depth_inputs():
    toks = tokenize("IF(ALL(Table), 1, 2)")
    opens = [t for t in toks if t.value == "("]
    closes = [t for t in toks if t.value == ")"]
    assert len(opens) == len(closes) == 2


@pytest.mark.parametrize("expr", ["", "   ", "\n"])
def test_tokenize_empty(expr):
    assert tokenize(expr) == []
