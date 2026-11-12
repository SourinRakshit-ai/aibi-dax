"""Tests for the dxa CLI."""

import json

import pytest

from aibi_dax.cli import main

MODEL = {
    "tables": [
        {"name": "Sales", "measures": [
            {"name": "Bad", "expression": "SUMX('Sales', CALCULATE([Amount]))"},
            {"name": "Good", "expression": "SUM('Sales'[Amount])"},
        ]},
    ],
}


@pytest.fixture()
def model_path(tmp_path):
    p = tmp_path / "model.json"
    p.write_text(json.dumps(MODEL), encoding="utf-8")
    return str(p)


def test_version():
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0


def test_metrics_human_and_json(capsys):
    assert main(["metrics", "SUM('Sales'[Amount])"]) == 0
    plain = capsys.readouterr().out
    assert "functions" in plain and "weight" in plain

    assert main(["metrics", "SUM('Sales'[Amount])", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["metrics"]["functions"] == 1


def test_rank_orders_measures(model_path, capsys):
    assert main(["rank", model_path, "--top", "2"]) == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert "Sales.Bad" in lines[0]
    assert len(lines) == 2


def test_rank_json_payload(model_path, capsys):
    assert main(["rank", model_path, "--top", "2", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload[0] == {"table": "Sales", "name": "Bad", "weight": payload[0]["weight"]}
    assert payload[0]["weight"] > payload[1]["weight"]


def test_rank_table_filter(tmp_path, capsys):
    other = dict(MODEL)
    other["tables"] = MODEL["tables"] + [
        {"name": "Other", "measures": [
            {"name": "Heavy", "expression": "SUMX('S', AVERAGEX('S', CALCULATE([x])))"},
        ]},
    ]
    p2 = tmp_path / "two.json"
    p2.write_text(json.dumps(other), encoding="utf-8")

    assert main(["rank", str(p2), "--table", "Other"]) == 0
    out = capsys.readouterr().out
    assert "Other.Heavy" in out and "Sales" not in out

    assert main(["rank", str(p2), "--table", "Nope"]) == 0
    assert capsys.readouterr().out.strip() == ""


def test_lint_model_json_and_clean_exit(model_path, capsys, tmp_path):
    assert main(["lint-model", model_path, "--json"]) == 1
    found = json.loads(capsys.readouterr().out)
    assert set(found) == {"Sales.Bad"}
    assert isinstance(found["Sales.Bad"], list)


def test_lint_model_table_filter(model_path, tmp_path, capsys):
    other = dict(MODEL)
    other["tables"] = MODEL["tables"] + [
        {"name": "Other", "measures": [
            {"name": "Worse", "expression": "SUMX('Sales', CALCULATE([Amount]))"},
        ]},
    ]
    p2 = tmp_path / "two.json"
    p2.write_text(json.dumps(other), encoding="utf-8")

    assert main(["lint-model", str(p2), "--table", "Other"]) == 1
    out = capsys.readouterr().out
    assert "Other.Worse:" in out and "Sales.Bad" not in out

    assert main(["lint-model", str(p2), "--table", "Nope"]) == 0
    assert "model is clean" in capsys.readouterr().out


def test_lint_model_rule_filter(model_path, capsys):
    assert main(["lint-model", model_path, "--rule", "calculate_inside_iterator"]) == 1
    out = capsys.readouterr().out
    assert "Sales.Bad:" in out and "CALCULATE inside" in out

    assert main(["lint-model", model_path, "--rule", "raw_division"]) == 0
    assert "model is clean" in capsys.readouterr().out

    assert main(["lint-model", model_path, "--rule", "single_column_iterator"]) == 0
    assert "model is clean" in capsys.readouterr().out

    assert main(["lint-model", model_path, "--rule", "no_such_rule"]) == 2
    assert "unknown rule" in capsys.readouterr().err


def test_lint_clean_and_dirty(capsys):
    assert main(["lint", "SUM('Sales'[Amount])"]) == 0
    assert "no findings" in capsys.readouterr().out
    assert main(["lint", "SUMX('Sales', CALCULATE([Amount]))"]) == 1
    assert "CALCULATE" in capsys.readouterr().out


def test_lint_json_dirty_and_clean(capsys):
    assert main(["lint", "SUMX('Sales', CALCULATE([Amount]))", "--json"]) == 1
    findings = json.loads(capsys.readouterr().out)
    assert isinstance(findings, list) and any("CALCULATE" in m for m in findings)
    assert main(["lint", "SUM('Sales'[Amount])", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == []


def test_parse_tree_output(capsys):
    assert main(["parse", "1 + [A]", "--tree"]) == 0
    assert capsys.readouterr().out == (
        "Binary op='+'\n"
        "  left:\n"
        "    Literal text='1'\n"
        "  right:\n"
        "    ColumnRef name='A'\n"
    )


def test_lint_rule_filter(capsys):
    assert main(["lint", "SUMX('Sales', CALCULATE([Amount]))", "--rule", "too_many_ifs"]) == 0
    assert "no findings" in capsys.readouterr().out

    assert main(["lint", "SUMX('Sales', CALCULATE([Amount]))", "--rule", "nested_iterators"]) == 0

    assert main(["lint", "SUMX('Sales', CALCULATE([Amount]))", "--rule", "calculate_inside_iterator"]) == 1
    assert "CALCULATE inside" in capsys.readouterr().out

    assert main(["lint", "[x]", "--rule", "nope"]) == 2
    assert "unknown rule" in capsys.readouterr().err


def test_lint_list_rules(capsys):
    assert main(["lint", "--list-rules"]) == 0
    out = capsys.readouterr().out
    lines = out.strip().splitlines()
    assert len(lines) == 15
    assert lines[0].startswith("calculate_inside_iterator")
    assert any("single_column_iterator" in l for l in lines)
    assert any("abs_negative_comparison" in l for l in lines)
    # every documented rule keeps its name column aligned
    assert all(len(l.split(maxsplit=1)[0]) <= 26 for l in lines)


def test_lint_without_expression_errors():
    assert main(["lint"]) == 2


def test_lint_model_exit_codes(model_path, capsys):
    assert main(["lint-model", model_path]) == 1
    assert "Sales.Bad:" in capsys.readouterr().out


def test_parse_tree_as_json(capsys):
    assert main(["parse", "1 + [A]", "--json"]) == 0
    tree = json.loads(capsys.readouterr().out)
    assert tree["op"] == "+"
    assert tree["left"] == {"text": "1"}
    assert tree["right"] == {"name": "A"}


def test_parse_error_is_exit_two(capsys):
    assert main(["parse", "1 +"]) == 2
    assert "error" in capsys.readouterr().err.lower()
