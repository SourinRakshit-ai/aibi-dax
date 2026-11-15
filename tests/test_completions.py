"""Completion scripts are generated from the parser, not hand-listed.

Each shell script must offer every subcommand, every option string and
every rule name that `_build_parser()` and `ALL_RULES` actually declare —
so a new flag or rule is completable the moment it lands, and a hard-coded
flag list in `completions.py` would fail here the moment it rots.
"""

from __future__ import annotations

import pytest

from aibi_dax.antipattern import ALL_RULES
from aibi_dax.cli import _build_parser, main
from aibi_dax.completions import SHELLS, option_strings, script, subcommands

COMMANDS = ("metrics", "rank", "explain", "lint", "lint-model", "parse")


def test_shells_offered_are_exactly_the_supported_three() -> None:
    assert SHELLS == ("bash", "zsh", "fish")


def test_subcommands_are_read_from_the_parser_structure() -> None:
    assert tuple(subcommands(_build_parser())) == COMMANDS


@pytest.mark.parametrize("shell", SHELLS)
def test_script_mentions_every_subcommand(shell: str) -> None:
    text = script(shell, _build_parser())
    for name in COMMANDS:
        assert name in text


@pytest.mark.parametrize("shell", SHELLS)
def test_script_covers_every_option_string(shell: str) -> None:
    """Top-level and per-subcommand options, straight from the actions.

    bash/zsh quote the literal strings (`--min-weight`); fish spells them
    as its own flags (`-l min-weight`, `-s h`).
    """
    parser = _build_parser()
    expected = option_strings(parser)
    for sub in subcommands(parser).values():
        expected += option_strings(sub)
    assert expected, "parser exposed no options at all"
    text = script(shell, parser)
    for option in expected:
        if shell == "fish":
            if option.startswith("--"):
                token = f"-l {option[2:]}"
            else:
                token = f"-s {option[1:]}"
        else:
            token = option
        assert token in text, f"{option!r} missing from {shell} script"


@pytest.mark.parametrize("shell", SHELLS)
def test_script_completes_every_rule_name(shell: str) -> None:
    """`--rule` and `explain` offer the `--list-rules` inventory."""
    text = script(shell, _build_parser())
    assert len(ALL_RULES) >= 17
    for rule in ALL_RULES:
        assert rule.__name__ in text


def test_unknown_shell_raises_value_error_listing_the_supported_three() -> None:
    with pytest.raises(ValueError) as exc:
        script("tcsh", _build_parser())
    assert "bash, zsh, fish" in str(exc.value)


def test_bash_script_is_wired_to_the_dxa_command() -> None:
    text = script("bash", _build_parser())
    assert text.startswith("# bash completion for dxa")
    assert "complete -F _dxa_complete dxa" in text


def test_zsh_script_carries_the_compdef_header() -> None:
    text = script("zsh", _build_parser())
    assert text.startswith("#compdef dxa")
    assert "compdef _dxa dxa" in text


def test_fish_script_defines_its_needs_command_helper() -> None:
    text = script("fish", _build_parser())
    assert "function __fish_dxa_needs_command" in text
    assert "__fish_seen_subcommand_from lint" in text


def test_scripts_are_not_empty_or_truncated() -> None:
    for shell in SHELLS:
        text = script(shell, _build_parser())
        assert text.endswith("\n")
        assert len(text.splitlines()) > 30


def test_completions_flag_prints_and_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    for shell in SHELLS:
        assert main(["--completions", shell]) == 0
        out = capsys.readouterr().out
        assert shell in out
        assert "lint-model" in out
        assert "filter_inside_aggregate" in out


def test_unknown_shell_is_a_usage_error(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--completions", "tcsh"]) == 2
    err = capsys.readouterr().err
    assert "usage: dxa" in err
    assert "bash, zsh, fish" in err


def test_completions_without_a_shell_shows_usage(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--completions"]) == 2
    err = capsys.readouterr().err
    assert "usage: dxa" in err
    assert "--completions needs a shell" in err
    assert capsys.readouterr().out == ""


def test_no_arguments_report_the_missing_command(capsys: pytest.CaptureFixture[str]) -> None:
    """Subparsers are optional now, so main reproduces argparse's error."""
    assert main([]) == 2
    err = capsys.readouterr().err
    assert "usage: dxa" in err
    assert "dxa: error: the following arguments are required: command" in err
