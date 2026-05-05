import json
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from zotero_cli_cc.cli import main


def _invoke(args: list[str], test_db_path: Path, json_output: bool = False):
    runner = CliRunner()
    base_args = ["--json"] if json_output else []
    env = {"ZOT_DATA_DIR": str(test_db_path.parent), "ZOT_FORMAT": "table"}
    return runner.invoke(main, base_args + args, env=env)


class TestSearch:
    def test_search_finds_item(self, test_db_path):
        result = _invoke(["search", "attention"], test_db_path)
        assert result.exit_code == 0
        assert "ATTN001" in result.output

    def test_search_json(self, test_db_path):
        result = _invoke(["search", "attention"], test_db_path, json_output=True)
        assert result.exit_code == 0
        data = json.loads(result.output)["data"]
        assert any(i["key"] == "ATTN001" for i in data)

    def test_search_no_results(self, test_db_path):
        result = _invoke(["search", "zzzznonexistent"], test_db_path)
        assert result.exit_code == 0
        assert "No results" in result.output

    def test_search_with_collection(self, test_db_path):
        result = _invoke(["search", "", "--collection", "Transformers"], test_db_path, json_output=True)
        data = json.loads(result.output)["data"]
        assert all(i["key"] == "ATTN001" for i in data)

    def test_search_with_command_level_limit(self, test_db_path):
        """--limit after subcommand should work (issue #7)."""
        result = _invoke(["search", "", "--limit", "1"], test_db_path, json_output=True)
        data = json.loads(result.output)["data"]
        assert len(data) == 1

    def test_search_collection_not_found(self, test_db_path):
        """Unknown collection should show error with available names (issue #8)."""
        result = _invoke(["search", "test", "--collection", "NonExistent"], test_db_path)
        assert result.exit_code != 0


class TestList:
    def test_list_all(self, test_db_path):
        result = _invoke(["list"], test_db_path)
        assert result.exit_code == 0
        assert "ATTN001" in result.output

    def test_list_with_collection(self, test_db_path):
        result = _invoke(["list", "--collection", "Machine Learning"], test_db_path, json_output=True)
        data = json.loads(result.output)["data"]
        assert len(data) >= 2

    def test_list_with_limit(self, test_db_path):
        result = _invoke(["--limit", "1", "list"], test_db_path, json_output=True)
        data = json.loads(result.output)["data"]
        assert len(data) == 1

    def test_list_with_command_level_limit(self, test_db_path):
        """--limit after subcommand should work (issue #7)."""
        result = _invoke(["list", "--limit", "1"], test_db_path, json_output=True)
        data = json.loads(result.output)["data"]
        assert len(data) == 1

    def test_list_collection_not_found(self, test_db_path):
        """Unknown collection should show error with available names (issue #8)."""
        result = _invoke(["list", "--collection", "NonExistent"], test_db_path)
        assert result.exit_code != 0
        assert "Collection 'NonExistent' not found" in result.output or "Collection 'NonExistent' not found" in (
            result.output + (result.stderr or "")
        )


class TestRead:
    def test_read_item(self, test_db_path):
        result = _invoke(["read", "ATTN001"], test_db_path)
        assert result.exit_code == 0
        assert "Attention Is All You Need" in result.output
        assert "Vaswani" in result.output

    def test_read_json(self, test_db_path):
        result = _invoke(["read", "ATTN001"], test_db_path, json_output=True)
        data = json.loads(result.output)["data"]
        assert data["title"] == "Attention Is All You Need"
        assert "notes" in data

    def test_read_nonexistent(self, test_db_path):
        result = _invoke(["read", "NONEXIST"], test_db_path)
        assert result.exit_code != 0
        assert "not found" in result.output.lower()


class TestExport:
    def test_export_bibtex(self, test_db_path):
        result = _invoke(["export", "ATTN001"], test_db_path)
        assert result.exit_code == 0
        assert "@article" in result.output
        assert "Attention" in result.output

    def test_export_ris(self, test_db_path):
        result = _invoke(["export", "ATTN001", "--format", "ris"], test_db_path)
        assert result.exit_code == 0
        assert "TY  - JOUR" in result.output
        assert "TI  - Attention" in result.output

    def test_export_json(self, test_db_path):
        result = _invoke(["export", "ATTN001", "--format", "json"], test_db_path)
        assert result.exit_code == 0
        # `export --format json` outputs the raw item dict, not an envelope.
        data = json.loads(result.output)
        assert "title" in data


class TestCiteCommand:
    def test_cite_apa_default(self, test_db_path):
        result = _invoke(["cite", "ATTN001", "--no-copy"], test_db_path)
        assert result.exit_code == 0
        assert "Vaswani" in result.output
        assert "2017" in result.output
        assert "Attention Is All You Need" in result.output

    def test_cite_nature(self, test_db_path):
        result = _invoke(["cite", "ATTN001", "--style", "nature", "--no-copy"], test_db_path)
        assert result.exit_code == 0
        assert "Vaswani" in result.output
        assert "10.5555/attention" in result.output

    def test_cite_vancouver(self, test_db_path):
        result = _invoke(["cite", "ATTN001", "--style", "vancouver", "--no-copy"], test_db_path)
        assert result.exit_code == 0
        assert "Vaswani A" in result.output
        assert "doi:10.5555/attention" in result.output

    def test_cite_not_found(self, test_db_path):
        result = _invoke(["cite", "NONEXIST", "--no-copy"], test_db_path)
        assert result.exit_code != 0
        assert "not found" in result.output

    def test_cite_copies_to_clipboard(self, test_db_path):
        with patch("zotero_cli_cc.commands.cite._copy_to_clipboard", return_value=True) as mock_copy:
            result = _invoke(["cite", "ATTN001"], test_db_path)
            assert result.exit_code == 0
            assert "copied to clipboard" in result.output
            mock_copy.assert_called_once()


class TestAddFromFile:
    def test_add_from_file_no_creds(self, test_db_path, tmp_path):
        doi_file = tmp_path / "dois.txt"
        doi_file.write_text("10.1038/s41586-023-06139-9\n")
        runner = CliRunner()
        # Use a non-existent profile dir to ensure no credentials are found
        env = {
            "ZOT_DATA_DIR": str(test_db_path.parent),
            "ZOT_LIBRARY_ID": "",
            "ZOT_API_KEY": "",
            "ZOT_FORMAT": "table",
        }
        result = runner.invoke(main, ["add", "--from-file", str(doi_file)], env=env)
        assert result.exit_code != 0
        assert "credentials not configured" in result.output.lower()

    def test_add_from_file_empty(self, test_db_path, tmp_path):
        doi_file = tmp_path / "empty.txt"
        doi_file.write_text("# just a comment\n\n")
        runner = CliRunner()
        env = {
            "ZOT_DATA_DIR": str(test_db_path.parent),
            "ZOT_LIBRARY_ID": "12345",
            "ZOT_API_KEY": "fake-key",
            "ZOT_FORMAT": "table",
        }
        result = runner.invoke(main, ["add", "--from-file", str(doi_file)], env=env)
        assert result.exit_code != 0
        assert "empty" in result.output.lower()

    def test_add_requires_input(self, test_db_path):
        runner = CliRunner()
        env = {
            "ZOT_DATA_DIR": str(test_db_path.parent),
            "ZOT_LIBRARY_ID": "12345",
            "ZOT_API_KEY": "fake-key",
            "ZOT_FORMAT": "table",
        }
        result = runner.invoke(main, ["add"], env=env)
        assert result.exit_code != 0
        assert "--from-file" in result.output
