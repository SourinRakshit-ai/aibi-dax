"""Load model dumps (TMDL-exported JSON) and enumerate measures."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

Model = dict[str, Any]
Measure = dict[str, Any]


def load_model(path: str | Path) -> Model:
    """Load a model JSON dump from disk; rejects non-object JSON."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise TypeError("model dump must be a JSON object")
    return data


def list_measures(model: Model) -> list[Measure]:
    """Yield every measure annotated with its table name."""
    out: list[Measure] = []
    for table in model.get("tables", []):
        for measure in table.get("measures", []):
            out.append({**measure, "table": table.get("name", "?")})
    return out
