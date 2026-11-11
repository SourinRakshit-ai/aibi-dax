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


def test_lint_model_json_and_clean_exit(model_path, capsys, tmp_path):
    assert main(["lint-model", model_path, "--json"]) == 1
    found = json.loads(capsys.readouterr().out)
    assert set(found) == {"Sales.Bad"}
    assert isinstance(found["Sales.Bad"], list)


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
