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


def test_too_many_ifs_skips_switch():
    stair = "IF(a, 1, IF(b, 2, IF(c, 3, 4)))"
    flat = "IF(a, 1, 2)"
    assert antipattern.too_many_ifs(stair) is not None
    assert antipattern.too_many_ifs(flat) is None


def test_raw_division_and_divide_escape():
    assert antipattern.raw_division("[A] / [B]") is not None
    assert antipattern.raw_division('DIVIDE([A], [B], "n/a")') is None
    assert antipattern.raw_division("path/no-slash") is not None


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


def test_all_first_argument_flags_the_all_aggregate():
    assert antipattern.all_first_argument("SUMX(ALL('Sales'), [Amount])") is not None
    assert antipattern.all_first_argument("AVERAGEX(FILTER(ALL('T'), [q] > 0), [x])") is not None
    assert antipattern.all_first_argument("CALCULATE([Amount], 'Sales'[Qty] > 0)") is None


def test_all_rules_cover_clean_expression():
    clean = "SUM('Sales'[Amount])"
    for rule in antipattern.ALL_RULES:
        assert rule(clean) is None


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
