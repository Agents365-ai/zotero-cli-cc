import json
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from zotero_cli_cc.cli import main


def test_note_read(test_db_path):
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["note", "ATTN001"],
        env={"ZOT_DATA_DIR": str(test_db_path.parent), "ZOT_FORMAT": "table"},
    )
    assert result.exit_code == 0
    assert "transformer architecture" in result.output


def test_note_read_json(test_db_path):
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["--json", "note", "ATTN001"],
        env={"ZOT_DATA_DIR": str(test_db_path.parent), "ZOT_FORMAT": "table"},
    )
    assert result.exit_code == 0
    data = json.loads(result.output)["data"]
    assert len(data) >= 1


@patch("zotero_cli_cc.commands.note.ZoteroWriter")
def test_note_add(mock_writer_cls, test_db_path):
    mock_writer = MagicMock()
    mock_writer_cls.return_value = mock_writer
    mock_writer.add_note.return_value = "NEWNOTE"

    runner = CliRunner()
    result = runner.invoke(
        main,
        ["note", "ATTN001", "--add", "New note"],
        env={
            "ZOT_DATA_DIR": str(test_db_path.parent),
            "ZOT_LIBRARY_ID": "123",
            "ZOT_API_KEY": "abc",
            "ZOT_FORMAT": "table",
        },
    )
    assert result.exit_code == 0
    mock_writer.add_note.assert_called_once()
