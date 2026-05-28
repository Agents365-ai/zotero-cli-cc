"""Tests for Zotero profile detection and bridge sideload install."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from zotero_cli_cc.cli import main
from zotero_cli_cc.core import bridge_install
from zotero_cli_cc.core.bridge_install import (
    install_bridge,
    plugin_id,
    uninstall_bridge,
)
from zotero_cli_cc.core.zotero_profile import ProfileNotFoundError, find_profile_dir


def _write_profiles_ini(base: Path, body: str) -> Path:
    base.mkdir(parents=True, exist_ok=True)
    (base / "profiles.ini").write_text(body, encoding="utf-8")
    return base


class TestFindProfileDir:
    def test_override_wins(self, tmp_path: Path):
        prof = tmp_path / "explicit"
        prof.mkdir()
        assert find_profile_dir(prof) == prof

    def test_override_missing_raises(self, tmp_path: Path):
        with pytest.raises(ProfileNotFoundError):
            find_profile_dir(tmp_path / "nope")

    def test_install_section_default(self, tmp_path: Path):
        prof = tmp_path / "Profiles" / "abcd.default"
        prof.mkdir(parents=True)
        _write_profiles_ini(
            tmp_path,
            "[Install1A]\nDefault=Profiles/abcd.default\nLocked=1\n\n"
            "[Profile0]\nName=default\nIsRelative=1\nPath=Profiles/abcd.default\nDefault=1\n",
        )
        assert find_profile_dir(base=tmp_path) == prof.resolve()

    def test_profile_default_flag(self, tmp_path: Path):
        prof = tmp_path / "Profiles" / "xyz.default"
        prof.mkdir(parents=True)
        _write_profiles_ini(
            tmp_path,
            "[Profile0]\nName=default\nIsRelative=1\nPath=Profiles/xyz.default\nDefault=1\n",
        )
        assert find_profile_dir(base=tmp_path) == prof.resolve()

    def test_single_profile_no_default(self, tmp_path: Path):
        prof = tmp_path / "Profiles" / "only.default"
        prof.mkdir(parents=True)
        _write_profiles_ini(
            tmp_path,
            "[Profile0]\nName=default\nIsRelative=1\nPath=Profiles/only.default\n",
        )
        assert find_profile_dir(base=tmp_path) == prof.resolve()

    def test_absolute_path(self, tmp_path: Path):
        prof = tmp_path / "abs_profile"
        prof.mkdir()
        _write_profiles_ini(
            tmp_path,
            f"[Profile0]\nName=default\nIsRelative=0\nPath={prof}\nDefault=1\n",
        )
        assert find_profile_dir(base=tmp_path) == prof

    def test_no_ini_raises(self, tmp_path: Path):
        with pytest.raises(ProfileNotFoundError):
            find_profile_dir(base=tmp_path / "empty")


class TestInstallUninstall:
    def test_install_writes_proxy_file(self, tmp_path: Path):
        info = install_bridge(tmp_path)
        pid = plugin_id()
        proxy = tmp_path / "extensions" / pid
        assert proxy.exists()
        assert proxy.read_text(encoding="utf-8") == str(bridge_install.bridge_source_dir().resolve())
        assert info["plugin_id"] == pid

    def test_install_refreshes_prefs(self, tmp_path: Path):
        prefs = tmp_path / "prefs.js"
        prefs.write_text(
            'user_pref("extensions.lastAppBuildId", "20240101");\n'
            'user_pref("extensions.lastAppVersion", "7.0");\n'
            'user_pref("some.other.pref", true);\n',
            encoding="utf-8",
        )
        info = install_bridge(tmp_path)
        assert info["prefs_refreshed"] is True
        remaining = prefs.read_text(encoding="utf-8")
        assert "lastAppBuildId" not in remaining
        assert "lastAppVersion" not in remaining
        assert "some.other.pref" in remaining

    def test_install_no_prefs_file(self, tmp_path: Path):
        info = install_bridge(tmp_path)
        assert info["prefs_refreshed"] is False

    def test_uninstall_removes_proxy(self, tmp_path: Path):
        install_bridge(tmp_path)
        info = uninstall_bridge(tmp_path)
        assert info["removed"]
        assert not (tmp_path / "extensions" / plugin_id()).exists()

    def test_uninstall_when_absent(self, tmp_path: Path):
        info = uninstall_bridge(tmp_path)
        assert info["removed"] == []


def _invoke(args: list[str], json_output: bool = False):
    runner = CliRunner()
    base = ["--json"] if json_output else []
    return runner.invoke(main, base + args, env={"ZOT_FORMAT": "table"})


class TestBridgeCLI:
    def test_install_cli(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("zotero_cli_cc.commands.bridge.is_zotero_running", lambda: False)
        result = _invoke(["bridge", "install", "--profile", str(tmp_path)])
        assert result.exit_code == 0
        assert "Installed bridge" in result.output
        assert (tmp_path / "extensions" / plugin_id()).exists()

    def test_install_refuses_when_running(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("zotero_cli_cc.commands.bridge.is_zotero_running", lambda: True)
        result = _invoke(["bridge", "install", "--profile", str(tmp_path)])
        assert result.exit_code == 3
        assert "running" in result.output.lower()

    def test_install_force_overrides_running(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("zotero_cli_cc.commands.bridge.is_zotero_running", lambda: True)
        result = _invoke(["bridge", "install", "--profile", str(tmp_path), "--force"])
        assert result.exit_code == 0

    def test_install_json(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("zotero_cli_cc.commands.bridge.is_zotero_running", lambda: False)
        result = _invoke(["bridge", "install", "--profile", str(tmp_path)], json_output=True)
        data = json.loads(result.output)["data"]
        assert data["plugin_id"] == plugin_id()
        assert Path(data["proxy_file"]).exists()

    def test_uninstall_cli(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("zotero_cli_cc.commands.bridge.is_zotero_running", lambda: False)
        _invoke(["bridge", "install", "--profile", str(tmp_path)])
        result = _invoke(["bridge", "uninstall", "--profile", str(tmp_path)])
        assert result.exit_code == 0
        assert "Removed bridge" in result.output

    def test_status_not_reachable(self, monkeypatch):
        def boom(*a, **k):
            from zotero_cli_cc.core.local_bridge import LocalBridgeError

            raise LocalBridgeError("down", code="not_reachable", retryable=True)

        monkeypatch.setattr("zotero_cli_cc.commands.bridge.ping", boom)
        result = _invoke(["bridge", "status"])
        assert result.exit_code == 5

    def test_status_ok(self, monkeypatch):
        monkeypatch.setattr(
            "zotero_cli_cc.commands.bridge.ping",
            lambda *a, **k: {"zotero_version": "7.0", "bridge_version": "0.1.0"},
        )
        result = _invoke(["bridge", "status"], json_output=True)
        data = json.loads(result.output)["data"]
        assert data["installed"] is True
        assert data["bridge"]["zotero_version"] == "7.0"
