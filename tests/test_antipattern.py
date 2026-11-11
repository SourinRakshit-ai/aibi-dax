"""Tests for the six anti-pattern rules."""

from aibi_dax import antipattern


def test_calculate_inside_iterator_flagged():
    bad = "SUMX('Sales', CALCULATE([Amount]))"
    assert antipattern.calculate_inside_iterator(bad) is not None


def test_calculate_outside_iterator_clean():
    good = "SUM('Sales'[Amount]) + CALCULATE([Amount])"
    assert antipattern.calculate_inside_iterator(good) is None


def test_calculate_after_iterator_paren_closes_is_fine():
    nested = "IF(SUMX('Sales', 0) > 1, CALCULATE([Amount]), 0)"
    assert antipattern.calculate_inside_iterator(nested) is None


def test_calculate_inside_iterator_ast_rules():
    """CALCULATE named in a string literal or below a non-iterator is data."""
    assert antipattern.calculate_inside_iterator("CONCATENATEX(S, \"use CALCULATE(x)\")") is None
    assert antipattern.calculate_inside_iterator("VAR c = CALCULATE([x]) RETURN c") is None
    assert antipattern.calculate_inside_iterator("VAR s = SUMX('S', CALCULATE([x])) RETURN s") is not None
    # unparseable text keeps the conservative token scan
    assert antipattern.calculate_inside_iterator("SUMX('S', CALCULATE(") is not None


def test_too_many_ifs_skips_switch():
    stair = "IF(a, 1, IF(b, 2, IF(c, 3, 4)))"
    flat = "IF(a, 1, 2)"
    assert antipattern.too_many_ifs(stair) is not None
    assert antipattern.too_many_ifs(flat) is None


def test_raw_division_and_divide_escape():
    assert antipattern.raw_division("[A] / [B]") is not None
    assert antipattern.raw_division('DIVIDE([A], [B], "n/a")') is None
    assert antipattern.raw_division("path/no-slash") is not None


def test_raw_division_ast_rules():
    """Constant denominators and literal slashes are not runtime traps."""
    assert antipattern.raw_division("[Amount] / 2") is None
    assert antipattern.raw_division("[Amount] / 0.5") is None
    assert antipattern.raw_division('"a/b"') is None
    assert antipattern.raw_division("1 / [Den]") is not None
    assert antipattern.raw_division("VAR t = [A] / [B] RETURN t") is not None
    # unparseable text keeps the conservative text scan
    assert antipattern.raw_division("a / /") is not None


def test_blank_comparison_prefers_isblank():
    assert antipattern.blank_comparison("[x] = BLANK()") is not None
    assert antipattern.blank_comparison("ISBLANK([x])") is None


def test_bare_all_table_vs_filters_argument():
    assert antipattern.bare_all_table("CALCULATE([x], ALL('Sales'))") is not None
    assert antipattern.bare_all_table("CALCULATE([x], ALL('Sales', ALLSELECTED('S')))") is None


def test_concat_ampersand_redundancy():
    bad = 'CONCATENATEX(Sales, "Q" & [Month], "-")'
    good = 'CONCATENATEX(Sales, [Month], "-")'
    assert antipattern.concat_ampersand(bad) is not None
    assert antipattern.concat_ampersand(good) is None


def test_concat_ampersand_ast_rules():
    """A '&' inside a string literal is data, not an operator."""
    assert antipattern.concat_ampersand('CONCATENATEX(Sales, "a&b", [x])') is None
    assert antipattern.concat_ampersand('CONCATENATEX(Sales, VAR k = "x" & [y] RETURN k)') is not None
    # unparseable text keeps the conservative text scan
    assert antipattern.concat_ampersand("CONCATENATEX(&") is not None


def test_all_first_argument_flags_the_all_aggregate():
    assert antipattern.all_first_argument("SUMX(ALL('Sales'), [Amount])") is not None
    assert antipattern.all_first_argument("AVERAGEX(FILTER(ALL('T'), [q] > 0), [x])") is not None
    assert antipattern.all_first_argument("CALCULATE([Amount], 'Sales'[Qty] > 0)") is None
def test_all_rules_cover_clean_expression():
    clean = "SUM('Sales'[Amount])"
    for rule in antipattern.ALL_RULES:
        assert rule(clean) is None


def test_lowercase_function_flags_mistyped_names():
    assert antipattern.lowercase_function("sum('Sales'[Amount])") is not None
    assert antipattern.lowercase_function('CONCATENATEX(S, "split(x)")') is None  # inside string
    assert antipattern.lowercase_function("SUM('S'[col (weird)])") is None  # inside brackets
    assert antipattern.lowercase_function("SUM('Sales'[Amount])") is None


def test_values_with_hasonevalue_needs_both_calls():
    pair = "IF(HASONEVALUE('S'[k]), VALUES('S'[k]), \"multi\")"
    solo = "IF(HASONEVALUE('S'[k]), 1, \"multi\")"
    assert antipattern.values_with_hasonevalue(pair) is not None
    assert antipattern.values_with_hasonevalue(solo) is None


def test_iferror_overuse_advises_explicit_contracts():
    assert antipattern.iferror_overuse('IFERROR([A] / [B], "n/a")') is not None
    assert antipattern.iferror_overuse('DIVIDE([A], [B], "n/a")') is None


def test_earlier_var_flags_the_deprecated_call():
    assert antipattern.earlier_var("CALCULATE([x], FILTER(T, EARLIER([k]) = [k]))") is not None
    assert antipattern.earlier_var("VAR k = [x] RETURN k") is None


def test_nested_iterators_flags_depth_two():
    assert antipattern.nested_iterators("SUMX('S', AVERAGEX('S', [x]))") is not None
    assert antipattern.nested_iterators("SUMX('S', [x])") is None


def test_nested_iterators_silent_on_parse_failure():
    # Unreducible text must never crash the rule engine.
    assert antipattern.nested_iterators("1 +") is None


def test_switch_without_default_flags_silent_blank():
    assert antipattern.switch_missing_default('SWITCH(TRUE(), [k]="a", 1, [k]="b", 2)') is not None
    assert antipattern.switch_missing_default('SWITCH(TRUE(), [k]="a", 1, [k]="b", 2, 0)') is None
    assert antipattern.switch_missing_default("SWITCH([k], 1, \"one\", \"other\")") is None
    assert antipattern.switch_missing_default("no switch here") is None


def test_single_column_iterator_collapses_to_plain_aggregate():
    msg = antipattern.single_column_iterator("SUMX('Sales', 'Sales'[Amount])")
    assert msg is not None and "SUM('Sales'[Amount])" in msg
    # mismatched table/column pairs are real iterations
    assert antipattern.single_column_iterator("SUMX('Sales', 'Items'[Amount])") is None
    # expressions, not bare column refs, are genuine per-row work
    assert antipattern.single_column_iterator("SUMX('Sales', [Amount] * 2)") is None
    assert antipattern.single_column_iterator("AVERAGEX('Sales', 'Sales'[Qty])") is not None
    assert antipattern.single_column_iterator("SUM('Sales'[Amount])") is None
    assert antipattern.single_column_iterator("SUMX(") is None


def test_walker_breadth_call_unary_var():
    """Every tree walker descends Call args, Unary operands and Var blocks."""
    # _raw_div_hit: Call arg, Unary operand, Var body
    assert antipattern.raw_division("IF(x, -[a] / [b])") is not None
    assert antipattern.raw_division("VAR t = [a] / [b] RETURN t") is not None
    assert antipattern.raw_division("VAR t = DIVIDE([a], [b]) RETURN t") is None
    assert antipattern.raw_division('MAX("a/b", [x])') is None
    # _eq_blank: Call arg, Unary operand, Var body
    assert antipattern.blank_comparison("IF(x, [y] = BLANK())") is not None
    assert antipattern.blank_comparison("-[y] = BLANK()") is not None
    assert antipattern.blank_comparison("VAR t = [y] = BLANK() RETURN t") is not None
    # _has_binary: Call arg, Unary operand, Var body
    assert antipattern.concat_ampersand('CONCATENATEX(S, IF(x, -("a" & [y])))') is not None
    assert antipattern.concat_ampersand('CONCATENATEX(S, VAR k = "x" & [y] RETURN k)') is not None
    # _iterator_depth: Unary and Var paths
    assert antipattern.nested_iterators("VAR s = SUMX('S', AVERAGEX('S', [x])) RETURN s") is not None
    assert antipattern.nested_iterators("VAR s = SUMX('S', [x]) RETURN s") is None


def test_unparseable_fallbacks_stay_conservative():
    """Regex fallbacks fire on the unparseable text the old rules scanned."""
    assert antipattern.raw_division("1 /") is not None
    assert antipattern.raw_division('DIVIDE("x / y")') is None
    assert antipattern.blank_comparison("= BLANK(") is not None
    assert antipattern.blank_comparison("no equality here =") is None
    assert antipattern.concat_ampersand("CONCATENATEX(S, 'a' & [b]") is not None
    assert antipattern.concat_ampersand("no iterator & here") is None
