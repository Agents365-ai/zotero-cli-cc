"""Tests for building the zot-cli-bridge .xpi and the `zot bridge` CLI."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

from click.testing import CliRunner

from zotero_cli_cc.cli import main
from zotero_cli_cc.core.bridge_install import (
    bridge_source_dir,
    build_xpi,
    default_xpi_path,
    plugin_id,
)


class TestBuildXpi:
    def test_source_dir_has_assets(self):
        src = bridge_source_dir()
        for f in ("manifest.json", "bootstrap.js", "icon.png"):
            assert (src / f).exists(), f"missing bundled asset: {f}"

    def test_plugin_id(self):
        assert plugin_id() == "zot-cli-bridge@zotero-cli-cc.org"

    def test_manifest_has_icons_and_update_url(self):
        # Zotero 8/9 reject a manifest without these as "incompatible".
        manifest = json.loads((bridge_source_dir() / "manifest.json").read_text())
        assert "icons" in manifest
        assert "update_url" in manifest["applications"]["zotero"]

    def test_build_xpi_contents(self, tmp_path: Path):
        out = build_xpi(tmp_path / "bridge.xpi")
        assert out.exists()
        with zipfile.ZipFile(out) as z:
            names = set(z.namelist())
            assert {"manifest.json", "bootstrap.js", "icon.png"} <= names
            # manifest inside the xpi must be valid JSON with the plugin id
            manifest = json.loads(z.read("manifest.json"))
            assert manifest["applications"]["zotero"]["id"] == plugin_id()

    def test_default_xpi_path(self):
        assert default_xpi_path().name == "zot-cli-bridge.xpi"


def _invoke(args: list[str], json_output: bool = False):
    runner = CliRunner()
    base = ["--json"] if json_output else []
    return runner.invoke(main, base + args, env={"ZOT_FORMAT": "table"})


class TestBridgeCLI:
    def test_install_builds_xpi(self, tmp_path: Path):
        out = tmp_path / "out.xpi"
        result = _invoke(["bridge", "install", "--output", str(out)])
        assert result.exit_code == 0
        assert out.exists()
        assert "Built bridge plugin" in result.output

    def test_install_json(self, tmp_path: Path):
        out = tmp_path / "out.xpi"
        result = _invoke(["bridge", "install", "--output", str(out)], json_output=True)
        data = json.loads(result.output)["data"]
        assert data["xpi"] == str(out)
        assert data["plugin_id"] == plugin_id()
        assert data["install_steps"]

    def test_uninstall_guides(self):
        result = _invoke(["bridge", "uninstall"])
        assert result.exit_code == 0
        assert "Tools -> Plugins" in result.output

    def test_uninstall_json(self):
        result = _invoke(["bridge", "uninstall"], json_output=True)
        data = json.loads(result.output)["data"]
        assert data["plugin_id"] == plugin_id()
        assert data["uninstall_steps"]

    def test_status_not_reachable(self, monkeypatch):
        def boom(*a, **k):
            from zotero_cli_cc.core.local_bridge import LocalBridgeError

            raise LocalBridgeError("down", code="not_reachable", retryable=True)

        monkeypatch.setattr("zotero_cli_cc.commands.bridge.ping", boom)
        result = _invoke(["bridge", "status"])
        assert result.exit_code == 5

    def test_status_missing(self, monkeypatch):
        def boom(*a, **k):
            from zotero_cli_cc.core.local_bridge import LocalBridgeError

            raise LocalBridgeError("not installed", code="bridge_missing", retryable=False)

        monkeypatch.setattr("zotero_cli_cc.commands.bridge.ping", boom)
        result = _invoke(["bridge", "status"])
        assert result.exit_code == 3

    def test_status_ok(self, monkeypatch):
        monkeypatch.setattr(
            "zotero_cli_cc.commands.bridge.ping",
            lambda *a, **k: {"zotero_version": "9.0.4", "bridge_version": "0.1.0"},
        )
        result = _invoke(["bridge", "status"], json_output=True)
        data = json.loads(result.output)["data"]
        assert data["installed"] is True
        assert data["bridge"]["zotero_version"] == "9.0.4"
