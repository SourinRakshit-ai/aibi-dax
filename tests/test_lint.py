"""Crossover tests: metrics + rules end-to-end against a realistic model."""

from aibi_dax import complexity, lint
from aibi_dax.antipattern import ALL_RULES, raw_division

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


def test_lint_findings_attribution_matches_expression_output():
    expr = "IF(a, 1, IF(b, 2, IF(c, 3, [D] / 0)))"
    pairs = lint.lint_findings(expr)
    assert pairs
    assert all(name in {r.__name__ for r in ALL_RULES} for name, _ in pairs)
    assert [msg for _, msg in pairs] == lint.lint_expression(expr)
    assert any(name == "too_many_ifs" for name, _ in pairs)


def test_lint_findings_respects_a_rule_filter():
    expr = "IF(a, 1, IF(b, 2, IF(c, 3, [D] / 0)))"
    assert all(name != "too_many_ifs" for name, _ in lint.lint_findings(expr, [raw_division]))
    (name, _), = lint.lint_findings("[x] / [y]", [raw_division])
    assert name == "raw_division"


MODEL = {
    "tables": [
        {
            "name": "Sales",
            "measures": [
                {
                    "name": "Iterator Calc",
                    "expression": "SUMX('Sales', CALCULATE([Amount]))",
                },
                {"name": "Clean Total", "expression": "SUM('Sales'[Amount])"},
            ],
        },
    ]
}


def test_lint_model_findings_attribution_and_keys():
    triples = lint.lint_model_findings(MODEL)
    assert triples
    keys = {key for key, _, _ in triples}
    assert keys == {"Sales.Iterator Calc"}
    rule, message = {(rule, message) for _, rule, message in triples}.pop()
    assert rule == "calculate_inside_iterator"
    assert "CALCULATE" in message


def test_lint_model_findings_respects_a_rule_filter():
    assert lint.lint_model_findings(MODEL, []) == []
