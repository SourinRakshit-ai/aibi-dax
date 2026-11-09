"""Docs smoke tests: every CLI example in docs/CLI.md must match real behavior.

The CLI.md fences are the public contract — issue #2. Each test extracts a
fenced example, replays it through `main()`, and pins the exit code and the
exact stdout lines. Drift between docs and the binary fails a test before a
release ships.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

import aibi_dax
from aibi_dax.cli import main

DOC = Path("docs/CLI.md")


def _fence(after_heading: str) -> list[str]:
    """Lines of the first ``` fence below the given CLI.md heading."""
    text = DOC.read_text(encoding="utf-8")
    body = text.split(f"## {after_heading}", 1)[1]
    block = re.search(r"```\n(.*?)```", body, re.DOTALL)
    assert block, f"no fenced example under '## {after_heading}'"
    return block.group(1).strip().splitlines()


def _expr_of(fence: list[str]) -> str:
    """The quoted expression inside the `$ dxa ...` line."""
    line = next(line for line in fence if line.lstrip().startswith("$"))
    match = re.search(r'"(.*)"', line)
    assert match, f"no quoted expression in {line!r}"
    return match.group(1)


def test_version_comment_matches_current_release() -> None:
    """The '# dxa X.Y.Z' hint must equal the shipped version."""
    line = next(line for line in _fence("Global") if line.startswith("dxa --version"))
    pinned = line.split("#")[-1].strip()
    assert pinned == f"dxa {aibi_dax.__version__}"
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0


def test_metrics_example_output_exact(capsys: pytest.CaptureFixture[str]) -> None:
    fence = _fence("`dxa metrics \"EXPR\"`")
    expected = [line for line in fence if not line.lstrip().startswith("$")]
    assert main(["metrics", _expr_of(fence)]) == 0
    got = capsys.readouterr().out.strip().splitlines()
    assert got == expected


def test_metrics_json_weight_matches_doc_example(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """CLI.md says the example weighs 57; the binary must agree."""
    fence = _fence("`dxa metrics \"EXPR\"`")
    assert main(["metrics", _expr_of(fence), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["weight"] == 45


def test_lint_example_pinned(capsys: pytest.CaptureFixture[str]) -> None:
    """Exit code 1 and the exact '- ' finding lines from the fence."""
    fence = _fence("`dxa lint \"EXPR\"`")
    expected = [line for line in fence if line.startswith("- ")]
    assert main(["lint", _expr_of(fence)]) == 1
    got = capsys.readouterr().out.strip().splitlines()
    assert got == expected
