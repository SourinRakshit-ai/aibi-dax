"""Tests for complexity metrics."""

from aibi_dax import complexity

SIMPLE = "[Amount] - [Discount]"
NESTED = "IF(SUMX(ALL('Sales'), IF([Qty] > 1, CALCULATE([Amount]), 0)), 1, 2)"


def test_count_functions_counts_call_sites():
    assert complexity.count_functions(SIMPLE) == 0
    # IF, SUMX, ALL, IF(inner), CALCULATE — five call sites in NESTED.
    assert complexity.count_functions(NESTED) == 5


def test_paren_depth_tracks_nesting():
    assert complexity.paren_depth(SIMPLE) == 0
    # IF( → SUMX( → ALL( → CALCULATE( reaches nesting level 4.
    assert complexity.paren_depth(NESTED) == 4


def test_report_metrics_shape():
    m = complexity.report("SUM('Sales'[Amount])")
    assert m["functions"] == 1
    assert m["depth"] == 1
    assert m["lines"] == 1


def test_weight_penalizes_iterators_recognized():
    plain = "SUM('Sales'[Amount])"
    iter_fun = "SUMX('Sales', [Amount] * [Qty])"
    assert complexity.weight(iter_fun) > complexity.weight(plain)


def test_rank_measures_orders_and_limits():
    model = {
        "tables": [
            {"name": "T", "measures": [
                {"name": "easy", "expression": SIMPLE},
                {"name": "hard", "expression": NESTED},
                {"name": "mid", "expression": "COUNTROWS('Sales')"},
            ]},
        ],
    }
    ranked = complexity.rank_measures(model, top=2)
    assert [name for _, name, _ in ranked] == ["hard", "mid"]
    assert all(w >= 0 for _, _, w in ranked)
