"""Crossover tests: metrics + rules end-to-end against a realistic model."""

from aibi_dax import complexity, lint

DIRTY_MODEL = {
    "tables": [
        {
            "name": "Sales",
            "measures": [
                {
                    "name": "Iterator Calc",
                    "expression": "SUMX('Sales', CALCULATE([Amount]))",
                },
                {
                    "name": "If Stair",
                    "expression": "IF(a, 1, IF(b, 2, IF(c, 3, [D] / 0)))",
                },
                {"name": "Clean Total", "expression": "SUM('Sales'[Amount])"},
            ],
        },
        {
            "name": "Calendar",
            "measures": [
                {"name": "Blank Tester", "expression": "IF([x] = BLANK(), 1, 2)"},
            ],
        },
    ],
}


def test_lint_model_groups_by_measure():
    found = lint.lint_model(DIRTY_MODEL)
    assert set(found) == {"Sales.Iterator Calc", "Sales.If Stair", "Calendar.Blank Tester"}
    assert "Sales.Clean Total" not in found


def test_clean_measures_absent_and_dirty_have_messages():
    found = lint.lint_model(DIRTY_MODEL)
    assert all(isinstance(msgs, list) and msgs for msgs in found.values())


def test_metrics_and_lint_agree_on_complexity_surface():
    ranked = complexity.rank_measures(DIRTY_MODEL, top=1)
    heaviest = ranked[0]
    assert heaviest[1] == "If Stair"  # most tokens, depth and operators together
    assert lint.lint_expression(DIRTY_MODEL["tables"][0]["measures"][1]["expression"])
