from __future__ import annotations

from click.testing import CliRunner

from zotero_cli_cc.cli import main


def test_completions_bash_exits_zero():
    runner = CliRunner()
    result = runner.invoke(main, ["completions", "bash"])
    assert result.exit_code == 0
    # Bash completions always produce output
    assert result.output.strip()
