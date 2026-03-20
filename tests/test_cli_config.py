from click.testing import CliRunner

from zotero_cli_cc.cli import main


def test_cli_version():
    runner = CliRunner()
    result = runner.invoke(main, ["--version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.output


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
        input="12345\nmy-api-key\n",
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
