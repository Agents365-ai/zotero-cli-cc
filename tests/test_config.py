import sys
from pathlib import Path

from zotero_cli_cc.config import AppConfig, load_config, save_config, detect_zotero_data_dir


def test_default_config():
    cfg = AppConfig()
    assert cfg.library_id == ""
    assert cfg.api_key == ""
    assert cfg.default_format == "table"
    assert cfg.default_limit == 50
    assert cfg.default_export_style == "bibtex"


def test_save_and_load_config(tmp_path):
    config_path = tmp_path / "config.toml"
    cfg = AppConfig(library_id="123", api_key="abc")
    save_config(cfg, config_path)
    loaded = load_config(config_path)
    assert loaded.library_id == "123"
    assert loaded.api_key == "abc"


def test_load_missing_config(tmp_path):
    config_path = tmp_path / "nonexistent.toml"
    cfg = load_config(config_path)
    assert cfg.library_id == ""


def test_detect_zotero_data_dir_with_override(tmp_path):
    db = tmp_path / "zotero.sqlite"
    db.touch()
    cfg = AppConfig(data_dir=str(tmp_path))
    result = detect_zotero_data_dir(cfg)
    assert result == tmp_path


def test_detect_zotero_data_dir_default(monkeypatch):
    result = detect_zotero_data_dir(AppConfig())
    if sys.platform == "win32":
        assert "Zotero" in str(result)
    else:
        assert result == Path.home() / "Zotero"


def test_config_has_write_credentials():
    cfg = AppConfig(library_id="123", api_key="abc")
    assert cfg.has_write_credentials is True
    cfg2 = AppConfig()
    assert cfg2.has_write_credentials is False


def test_get_data_dir_env_override(tmp_path, monkeypatch):
    from zotero_cli_cc.config import get_data_dir
    monkeypatch.setenv("ZOT_DATA_DIR", str(tmp_path))
    cfg = AppConfig(data_dir="/some/other/path")
    result = get_data_dir(cfg)
    assert result == tmp_path


def test_get_data_dir_falls_back_to_config(monkeypatch, tmp_path):
    from zotero_cli_cc.config import get_data_dir
    monkeypatch.delenv("ZOT_DATA_DIR", raising=False)
    cfg = AppConfig(data_dir=str(tmp_path))
    result = get_data_dir(cfg)
    assert result == tmp_path
