from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from zotero_cli_cc.cli import main

WRITE_ENV = {"ZOT_LIBRARY_ID": "123", "ZOT_API_KEY": "abc"}


@patch("zotero_cli_cc.commands.add.ZoteroWriter")
def test_add_by_doi(mock_writer_cls):
    mock_writer = MagicMock()
    mock_writer_cls.return_value = mock_writer
    mock_writer.add_item.return_value = "NEW001"

    runner = CliRunner()
    result = runner.invoke(main, ["add", "--doi", "10.1234/test"], env=WRITE_ENV)
    assert result.exit_code == 0
    assert "NEW001" in result.output


@patch("zotero_cli_cc.commands.delete.ZoteroWriter")
def test_delete_with_confirm(mock_writer_cls):
    mock_writer = MagicMock()
    mock_writer_cls.return_value = mock_writer

    runner = CliRunner()
    result = runner.invoke(main, ["delete", "K1", "--yes"], env=WRITE_ENV)
    assert result.exit_code == 0
    mock_writer.delete_item.assert_called_once_with("K1")


@patch("zotero_cli_cc.commands.delete.ZoteroWriter")
def test_delete_without_confirm(mock_writer_cls):
    # Without --yes on non-tty stdin (CliRunner uses StringIO), `delete` refuses
    # the operation and exits EXIT_VALIDATION (3) — guards against unattended
    # destructive deletes. Confirmation flow is exercised in interactive tests.
    runner = CliRunner()
    result = runner.invoke(main, ["delete", "K1"], input="n\n", env=WRITE_ENV)
    assert result.exit_code == 3
    mock_writer_cls.return_value.delete_item.assert_not_called()


@patch("zotero_cli_cc.commands.tag.ZoteroWriter")
def test_tag_add(mock_writer_cls):
    mock_writer = MagicMock()
    mock_writer_cls.return_value = mock_writer

    runner = CliRunner()
    result = runner.invoke(main, ["tag", "K1", "--add", "newtag"], env=WRITE_ENV)
    assert result.exit_code == 0
    mock_writer.add_tags.assert_called_once_with("K1", ["newtag"])


def test_tag_list(test_db_path):
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["tag", "ATTN001"],
        env={"ZOT_DATA_DIR": str(test_db_path.parent), "ZOT_FORMAT": "table"},
    )
    assert result.exit_code == 0
    assert "transformer" in result.output


def test_collection_list(test_db_path):
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["collection", "list"],
        env={"ZOT_DATA_DIR": str(test_db_path.parent), "ZOT_FORMAT": "table"},
    )
    assert result.exit_code == 0
    assert "Machine Learning" in result.output


@patch("zotero_cli_cc.commands.collection.ZoteroWriter")
def test_collection_create(mock_writer_cls):
    mock_writer = MagicMock()
    mock_writer_cls.return_value = mock_writer
    mock_writer.create_collection.return_value = "NEWCOL"

    runner = CliRunner()
    result = runner.invoke(main, ["collection", "create", "New Col"], env=WRITE_ENV)
    assert result.exit_code == 0
    assert "NEWCOL" in result.output
