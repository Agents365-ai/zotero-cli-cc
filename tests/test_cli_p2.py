import json
from pathlib import Path

from click.testing import CliRunner

from zotero_cli_cc.cli import main


def test_summarize(test_db_path):
    runner = CliRunner()
    result = runner.invoke(
        main, ["summarize", "ATTN001"],
        env={"ZOT_DATA_DIR": str(test_db_path.parent)},
    )
    assert result.exit_code == 0
    assert "Attention Is All You Need" in result.output
    assert "Vaswani" in result.output


def test_summarize_json(test_db_path):
    runner = CliRunner()
    result = runner.invoke(
        main, ["--json", "summarize", "ATTN001"],
        env={"ZOT_DATA_DIR": str(test_db_path.parent)},
    )
    data = json.loads(result.output)
    assert data["title"] == "Attention Is All You Need"


def test_relate(test_db_path):
    runner = CliRunner()
    result = runner.invoke(
        main, ["relate", "ATTN001"],
        env={"ZOT_DATA_DIR": str(test_db_path.parent)},
    )
    assert result.exit_code == 0
    assert "BERT002" in result.output


def test_pdf_no_attachment(test_db_path):
    runner = CliRunner()
    result = runner.invoke(
        main, ["pdf", "DEEP003"],
        env={"ZOT_DATA_DIR": str(test_db_path.parent)},
    )
    assert result.exit_code == 0
    assert "no pdf" in result.output.lower() or "not found" in result.output.lower()


def test_pdf_invalid_page_range_non_numeric(test_db_path):
    runner = CliRunner()
    result = runner.invoke(
        main, ["pdf", "--pages", "abc", "DEEP003"],
        env={"ZOT_DATA_DIR": str(test_db_path.parent)},
    )
    assert result.exit_code == 0
    assert "invalid page range" in result.output.lower()


def test_pdf_invalid_page_range_reversed(test_db_path):
    runner = CliRunner()
    result = runner.invoke(
        main, ["pdf", "--pages", "5-2", "DEEP003"],
        env={"ZOT_DATA_DIR": str(test_db_path.parent)},
    )
    assert result.exit_code == 0
    assert "invalid page range" in result.output.lower()


def test_pdf_invalid_page_range_zero(test_db_path):
    runner = CliRunner()
    result = runner.invoke(
        main, ["pdf", "--pages", "0-3", "DEEP003"],
        env={"ZOT_DATA_DIR": str(test_db_path.parent)},
    )
    assert result.exit_code == 0
    assert "invalid page range" in result.output.lower()
