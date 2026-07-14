from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from zotero_cli_cc.cli import main


def test_summarize_all_basic(test_db_path: Path):
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["summarize-all", "--limit", "2"],
        env={"ZOT_DATA_DIR": str(test_db_path.parent), "ZOT_FORMAT": "table"},
    )
    assert result.exit_code == 0
    # Should produce JSON output with items
    assert "title" in result.output


def test_summarize_all_json(test_db_path: Path):
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["--json", "summarize-all", "--limit", "1"],
        env={"ZOT_DATA_DIR": str(test_db_path.parent), "ZOT_FORMAT": "table"},
    )
    assert result.exit_code == 0
    assert '"ok"' in result.output
    assert '"count"' in result.output
