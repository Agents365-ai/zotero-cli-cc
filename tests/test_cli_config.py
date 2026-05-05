from click.testing import CliRunner

from zotero_cli_cc import __version__
from zotero_cli_cc.cli import main


def test_cli_version():
    runner = CliRunner()
    result = runner.invoke(main, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output


def test_cli_help():
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "config" in result.output


def test_config_init(tmp_path):
    runner = CliRunner()
    config_path = tmp_path / "config.toml"
    result = runner.invoke(
        main,
        ["config", "init", "--config-path", str(config_path)],
        input="12345\nmy-api-key\n\n",
    )
    assert result.exit_code == 0
    assert config_path.exists()
    content = config_path.read_text()
    assert "12345" in content
    assert "my-api-key" in content


def test_config_show(tmp_path):
    runner = CliRunner()
    config_path = tmp_path / "config.toml"
    config_path.write_text('[zotero]\nlibrary_id = "123"\napi_key = "abc"\n')
    result = runner.invoke(main, ["config", "show", "--config-path", str(config_path)])
    assert result.exit_code == 0
    assert "123" in result.output


def test_cache_list_empty(tmp_path):
    from zotero_cli_cc.core import pdf_cache as pdf_cache_module

    old_default = pdf_cache_module.DEFAULT_CACHE_PATH
    try:
        pdf_cache_module.DEFAULT_CACHE_PATH = tmp_path / "pdf_cache.sqlite"
        runner = CliRunner()
        result = runner.invoke(main, ["config", "cache", "list"])
        assert result.exit_code == 0
        assert "Cache is empty." in result.output
    finally:
        pdf_cache_module.DEFAULT_CACHE_PATH = old_default


def test_cache_list_populated(tmp_path):
    from zotero_cli_cc.core import pdf_cache as pdf_cache_module
    from zotero_cli_cc.core.pdf_cache import PdfCache

    old_default = pdf_cache_module.DEFAULT_CACHE_PATH
    try:
        pdf_cache_module.DEFAULT_CACHE_PATH = tmp_path / "pdf_cache.sqlite"
        cache = PdfCache()
        cache._conn.execute(
            "INSERT INTO pdf_cache (pdf_path, mtime, content, extracted_at) VALUES (?, ?, ?, ?)",
            ("/path/to/paper1.pdf", 1.0, "This is the extracted text content.", "2024-01-15T10:30:00+00:00"),
        )
        cache._conn.commit()
        cache.close()

        runner = CliRunner()
        result = runner.invoke(main, ["config", "cache", "list"])
        assert result.exit_code == 0
        assert "paper1.pdf" in result.output
        assert "This is the extracted text content." in result.output
    finally:
        pdf_cache_module.DEFAULT_CACHE_PATH = old_default


def test_cache_list_json(tmp_path):
    import json

    from zotero_cli_cc.core import pdf_cache as pdf_cache_module
    from zotero_cli_cc.core.pdf_cache import PdfCache

    old_default = pdf_cache_module.DEFAULT_CACHE_PATH
    try:
        pdf_cache_module.DEFAULT_CACHE_PATH = tmp_path / "pdf_cache.sqlite"
        cache = PdfCache()
        cache._conn.execute(
            "INSERT INTO pdf_cache (pdf_path, mtime, content, extracted_at) VALUES (?, ?, ?, ?)",
            ("/path/to/paper2.pdf", 1.0, "Short text.", "2024-06-01T08:00:00+00:00"),
        )
        cache._conn.commit()
        cache.close()

        runner = CliRunner()
        result = runner.invoke(main, ["--json", "config", "cache", "list"])
        assert result.exit_code == 0
        # `config cache list --json` is now routed through the agent envelope.
        data = json.loads(result.output)["data"]
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["pdf_basename"] == "/path/to/paper2.pdf"
        assert data[0]["text_length"] == 11
        assert data[0]["preview"] == "Short text."
    finally:
        pdf_cache_module.DEFAULT_CACHE_PATH = old_default
