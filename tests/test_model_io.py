"""Tests for model loading and measure enumeration."""

from aibi_dax import model_io

READY_FEATURES = {
    "tables": [
        {
            "name": "Calendar",
            "columns": [{"name": "Date"}],
            "measures": [
                {"name": "Calendar fans", "expression": "DISTINCTCOUNT(Calendar[Date])"},
            ],
        },
        {
            "name": "Sales",
            "columns": [{"name": "Amount"}],
            "measures": [
                {"name": "Revenue", "expression": "[Amount Fan]"},
            ],
        },
    ],
}


def test_load_model_rejects_arrays(tmp_path):
    bad = tmp_path / "model.json"
    bad.write_text("[]", encoding="utf-8")
    try:
        model_io.load_model(str(bad))
    except TypeError as exc:
        assert "JSON object" in str(exc)
    else:
        raise AssertionError("expected TypeError for non-object JSON")


def test_list_measures_flattens_with_table_annotation():
    measures = model_io.list_measures(READY_FEATURES)
    assert [(m["table"], m["name"]) for m in measures] == [
        ("Calendar", "Calendar fans"),
        ("Sales", "Revenue"),
    ]
