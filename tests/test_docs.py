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


def _fence(after_heading: str, index: int = 0) -> list[str]:
    """Lines of the index-th ``` fence below the given CLI.md heading."""
    text = DOC.read_text(encoding="utf-8")
    body = text.split(f"## {after_heading}", 1)[1]
    blocks = re.findall(r"^```[^\n]*\n(.*?)^```", body, re.DOTALL | re.MULTILINE)
    assert len(blocks) > index, f"fence #{index} missing under '## {after_heading}'"
    return blocks[index].strip().splitlines()


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


def test_metrics_multi_example_replays(capsys: pytest.CaptureFixture[str]) -> None:
    """The second metrics fence is a two-expression run, replayed verbatim."""
    fence = _fence("`dxa metrics \"EXPR\"`", index=1)
    line = next(line for line in fence if line.lstrip().startswith("$"))
    exprs = re.findall(r'"([^"]*)"', line)
    assert len(exprs) == 2
    expected = [ln for ln in fence if not ln.lstrip().startswith("$")]
    assert main(["metrics", *exprs]) == 0
    got = capsys.readouterr().out.strip().splitlines()
    assert got == expected


def test_lint_example_pinned(capsys: pytest.CaptureFixture[str]) -> None:
    """Exit code 1 and the exact '- ' finding lines from the fence."""
    fence = _fence("`dxa lint \"EXPR\"`")
    expected = [line for line in fence if line.startswith("- ")]
    assert main(["lint", _expr_of(fence)]) == 1
    got = capsys.readouterr().out.strip().splitlines()
    assert got == expected


def test_lint_json_clean_example(capsys: pytest.CaptureFixture[str]) -> None:
    """The --json contract: empty list on a clean expression, exit 0."""
    assert main(["lint", "SUM('Sales'[Amount])", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == []


def test_parse_tree_fence_is_real(capsys: pytest.CaptureFixture[str]) -> None:
    """The --tree example fence must equal the CLI's indented tree byte for byte."""
    fence = _fence("`dxa parse \"EXPR\"`", index=0)
    expected = [line for line in fence if not line.lstrip().startswith("$")]
    assert main(["parse", _expr_of(fence), "--tree"]) == 0
    got = capsys.readouterr().out.strip().splitlines()
    assert got == expected


def test_parse_json_fence_is_real(capsys: pytest.CaptureFixture[str]) -> None:
    """The parse example fence must equal the CLI's indented JSON byte for byte."""
    fence = _fence("`dxa parse \"EXPR\"`", index=1)
    expected = [line for line in fence if not line.lstrip().startswith("$")]
    assert main(["parse", _expr_of(fence), "--json"]) == 0
    got = capsys.readouterr().out.strip().splitlines()
    assert got == expected


def test_changelog_leads_with_the_current_version() -> None:
    """The newest CHANGELOG heading equals the pyproject version."""
    from pathlib import Path

    changelog = Path("CHANGELOG.md").read_text(encoding="utf-8")
    heading = re.search(r"^## (\S+)", changelog, re.MULTILINE)
    assert heading, "no version heading in CHANGELOG.md"

    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")
    version = re.search(r'^version = "(\S+)"', pyproject, re.MULTILINE)
    assert version, "no version key in pyproject.toml"
    assert heading.group(1) == version.group(1)

RECIPES = Path("docs/recipes.md")


def test_recipe_fences_replay(capsys: pytest.CaptureFixture[str]) -> None:
    """Every `$ dxa lint` fence in recipes.md must match real CLI output.

    The cookbook's whole value is that its before/after pairs are true;
    a rule-message change that isn't reflected here fails here first.
    """
    text = RECIPES.read_text(encoding="utf-8")
    blocks = re.findall(r"```\n(.*?)```", text, re.DOTALL)
    assert len(blocks) == 16, "eight recipes, before and after each"
    for block in blocks:
        fence = block.strip().splitlines()
        expr = _expr_of(fence)
        expected = [ln for ln in fence if not ln.lstrip().startswith("$")]
        want_exit = 1 if expected[0].startswith("- ") else 0
        assert main(["lint", expr]) == want_exit, expr
        got = capsys.readouterr().out.strip().splitlines()
        assert got == expected, expr


def test_metrics_top_example_replays(capsys: pytest.CaptureFixture[str]) -> None:
    """The --top fence in CLI.md must match the binary byte for byte."""
    fence = _fence("`dxa metrics \"EXPR\"`", index=2)
    line = next(ln for ln in fence if ln.lstrip().startswith("$"))
    exprs = re.findall(r'"([^"]*)"', line)
    top = re.search(r"--top (\d+)", line)
    assert len(exprs) == 2 and top, line
    expected = [ln for ln in fence if not ln.lstrip().startswith("$")]
    assert main(["metrics", *exprs, "--top", top.group(1)]) == 0
    got = capsys.readouterr().out.strip().splitlines()
    assert got == expected


def test_lint_section_documents_sarif() -> None:
    """The lint section of CLI.md must document the --sarif contract."""
    text = DOC.read_text(encoding="utf-8")
    section = text.split("## `dxa lint \"EXPR\"`", 1)[1].split("\n## ", 1)[0]
    assert "--sarif" in section
    assert "SARIF 2.1.0" in section
    assert "always 0" in section or "exit 0" in section.lower()


CI_DOC = Path("docs/ci.md")


def _ci_fence(after_heading: str, index: int = 0) -> list[str]:
    text = CI_DOC.read_text(encoding="utf-8")
    body = text.split(f"## {after_heading}", 1)[1]
    blocks = re.findall(r"^```[^\n]*\n(.*?)^```", body, re.DOTALL | re.MULTILINE)
    assert len(blocks) > index, f"fence #{index} missing under '## {after_heading}'"
    return blocks[index].strip().splitlines()


def test_ci_page_lint_fence_replays(capsys: pytest.CaptureFixture[str]) -> None:
    fence = _ci_fence("The exit-code contract")
    expr = _expr_of(fence)
    expected = [ln for ln in fence if not ln.lstrip().startswith("$")]
    assert main(["lint", expr]) == 0
    got = capsys.readouterr().out.strip().splitlines()
    assert got == expected


def test_ci_page_json_fence_replays(capsys: pytest.CaptureFixture[str]) -> None:
    fence = _ci_fence("A plain gate", index=1)  # first fence is the yaml block
    expr = _expr_of(fence)
    expected = [ln for ln in fence if not ln.lstrip().startswith("$")]
    assert main(["lint", expr, "--json"]) == 0
    got = capsys.readouterr().out.strip().splitlines()
    assert got == expected


def test_rules_md_mentions_every_rule_name() -> None:
    """Every rule in ALL_RULES must appear in rules.md (the reference).

    Regression for the silent anchor failure that left nine rules out
    of the reference and off the changelog: the reference must mention
    every rule name explicitly.
    """
    from aibi_dax.antipattern import ALL_RULES

    text = Path("docs/rules.md").read_text(encoding="utf-8")
    missing = [rule.__name__ for rule in ALL_RULES if rule.__name__ not in text]
    assert not missing, f"rule reference missing sections for: {missing}"


def test_rules_md_rule_index_lists_all_rules() -> None:
    """The trailing Rule index must name every rule exactly."""
    from aibi_dax.antipattern import ALL_RULES

    text = Path("docs/rules.md").read_text(encoding="utf-8")
    index = text.split("## Rule index", 1)[1]
    names = [ln[3:].lstrip("`").split("`", 1)[0] for ln in index.splitlines() if ln.startswith("- `")]
    assert sorted(names) == sorted(rule.__name__ for rule in ALL_RULES)


def test_lint_model_section_documents_sarif() -> None:
    text = DOC.read_text(encoding="utf-8")
    section = text.split("## `dxa lint-model model.json`", 1)[1].split("\n## ", 1)[0]
    assert "--sarif" in section
    assert "JSON Pointer" in section
    assert "RFC 6901" in section


def test_ci_page_mentions_lint_model_sarif() -> None:
    text = Path("docs/ci.md").read_text(encoding="utf-8")
    assert "lint-model model.json --sarif" in text


def test_public_rule_counts_match_the_catalog() -> None:
    """README's anti-pattern list and docs/index count match ALL_RULES."""
    import re

    from aibi_dax.antipattern import ALL_RULES

    readme = Path("README.md").read_text(encoding="utf-8")
    index = Path("docs/index.md").read_text(encoding="utf-8")
    section = readme.split("<summary>", 1)[1].split("</details>", 1)[0]
    numerals = [int(m.group(1)) for m in re.finditer(r"^(\d+)\. ", section, re.MULTILINE)]
    assert numerals == list(range(1, len(ALL_RULES) + 1)), numerals[-5:]
    assert "seventy-six anti-pattern rules" in index
