"""Tests for workspace feature."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from zotero_cli_cc.cli import main
from zotero_cli_cc.core.workspace import (
    Workspace,
    WorkspaceItem,
    delete_workspace,
    list_workspaces,
    load_workspace,
    save_workspace,
    validate_name,
    workspace_exists,
    workspaces_dir,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _invoke(args: list[str], json_output: bool = False):
    runner = CliRunner()
    base = ["--json"] if json_output else []
    env = {"ZOT_DATA_DIR": str(FIXTURES_DIR)}
    return runner.invoke(main, base + args, env=env)


# --- Core unit tests ---


class TestValidateName:
    def test_valid_names(self):
        assert validate_name("llm-safety") is True
        assert validate_name("protein-folding") is True
        assert validate_name("topic1") is True
        assert validate_name("a") is True
        assert validate_name("my-long-workspace-name") is True

    def test_invalid_names(self):
        assert validate_name("") is False
        assert validate_name("LLM-Safety") is False
        assert validate_name("has spaces") is False
        assert validate_name("under_score") is False
        assert validate_name("-leading") is False
        assert validate_name("trailing-") is False
        assert validate_name("double--dash") is False
        assert validate_name("has.dot") is False


class TestWorkspaceModel:
    def test_has_item(self):
        ws = Workspace(name="test", created="2026-01-01", items=[
            WorkspaceItem(key="ABC", title="Paper A", added="2026-01-01"),
        ])
        assert ws.has_item("ABC") is True
        assert ws.has_item("XYZ") is False

    def test_add_item(self):
        ws = Workspace(name="test", created="2026-01-01")
        assert ws.add_item("ABC", "Paper A") is True
        assert len(ws.items) == 1
        assert ws.items[0].key == "ABC"
        assert ws.items[0].title == "Paper A"

    def test_add_item_duplicate(self):
        ws = Workspace(name="test", created="2026-01-01", items=[
            WorkspaceItem(key="ABC", title="Paper A", added="2026-01-01"),
        ])
        assert ws.add_item("ABC", "Paper A") is False
        assert len(ws.items) == 1

    def test_remove_item(self):
        ws = Workspace(name="test", created="2026-01-01", items=[
            WorkspaceItem(key="ABC", title="Paper A", added="2026-01-01"),
            WorkspaceItem(key="DEF", title="Paper B", added="2026-01-01"),
        ])
        assert ws.remove_item("ABC") is True
        assert len(ws.items) == 1
        assert ws.items[0].key == "DEF"

    def test_remove_item_not_found(self):
        ws = Workspace(name="test", created="2026-01-01")
        assert ws.remove_item("XYZ") is False


class TestWorkspaceIO:
    def test_save_and_load(self, tmp_path):
        with patch("zotero_cli_cc.core.workspace.workspaces_dir", return_value=tmp_path):
            ws = Workspace(
                name="test-ws",
                created="2026-03-29T10:00:00+00:00",
                description="Test workspace",
                items=[
                    WorkspaceItem(key="ABC123", title="Paper A", added="2026-03-29T10:05:00+00:00"),
                    WorkspaceItem(key="DEF456", title="Paper B", added="2026-03-29T10:06:00+00:00"),
                ],
            )
            save_workspace(ws)
            loaded = load_workspace("test-ws")

        assert loaded.name == "test-ws"
        assert loaded.created == "2026-03-29T10:00:00+00:00"
        assert loaded.description == "Test workspace"
        assert len(loaded.items) == 2
        assert loaded.items[0].key == "ABC123"
        assert loaded.items[0].title == "Paper A"
        assert loaded.items[1].key == "DEF456"

    def test_load_nonexistent(self, tmp_path):
        with patch("zotero_cli_cc.core.workspace.workspaces_dir", return_value=tmp_path):
            with pytest.raises(FileNotFoundError):
                load_workspace("nonexistent")

    def test_list_workspaces(self, tmp_path):
        with patch("zotero_cli_cc.core.workspace.workspaces_dir", return_value=tmp_path):
            save_workspace(Workspace(name="ws-a", created="2026-01-01"))
            save_workspace(Workspace(name="ws-b", created="2026-01-02"))
            result = list_workspaces()
        assert len(result) == 2
        assert result[0].name == "ws-a"
        assert result[1].name == "ws-b"

    def test_list_empty(self, tmp_path):
        with patch("zotero_cli_cc.core.workspace.workspaces_dir", return_value=tmp_path):
            result = list_workspaces()
        assert result == []

    def test_delete_workspace(self, tmp_path):
        with patch("zotero_cli_cc.core.workspace.workspaces_dir", return_value=tmp_path):
            save_workspace(Workspace(name="doomed", created="2026-01-01"))
            assert workspace_exists("doomed")
            delete_workspace("doomed")
            assert not workspace_exists("doomed")

    def test_delete_nonexistent(self, tmp_path):
        with patch("zotero_cli_cc.core.workspace.workspaces_dir", return_value=tmp_path):
            with pytest.raises(FileNotFoundError):
                delete_workspace("nonexistent")

    def test_save_with_special_chars_in_title(self, tmp_path):
        with patch("zotero_cli_cc.core.workspace.workspaces_dir", return_value=tmp_path):
            ws = Workspace(
                name="test-special",
                created="2026-01-01",
                items=[
                    WorkspaceItem(key="X1", title='Paper with "quotes" and \\backslash', added="2026-01-01"),
                ],
            )
            save_workspace(ws)
            loaded = load_workspace("test-special")
        assert loaded.items[0].title == 'Paper with "quotes" and \\backslash'


# --- CLI integration tests ---


class TestWorkspaceCLI:
    def test_new_workspace(self, tmp_path):
        with patch("zotero_cli_cc.core.workspace.workspaces_dir", return_value=tmp_path):
            result = _invoke(["workspace", "new", "test-ws", "--description", "A test"])
        assert result.exit_code == 0
        assert "Workspace created: test-ws" in result.output

    def test_new_workspace_invalid_name(self, tmp_path):
        with patch("zotero_cli_cc.core.workspace.workspaces_dir", return_value=tmp_path):
            result = _invoke(["workspace", "new", "Bad Name"])
        assert result.exit_code == 0
        assert "Invalid workspace name" in result.output

    def test_new_workspace_duplicate(self, tmp_path):
        with patch("zotero_cli_cc.core.workspace.workspaces_dir", return_value=tmp_path):
            _invoke(["workspace", "new", "test-ws"])
            result = _invoke(["workspace", "new", "test-ws"])
        assert "already exists" in result.output

    def test_list_workspaces_empty(self, tmp_path):
        with patch("zotero_cli_cc.core.workspace.workspaces_dir", return_value=tmp_path):
            result = _invoke(["workspace", "list"])
        assert "No workspaces found" in result.output

    def test_list_workspaces(self, tmp_path):
        with patch("zotero_cli_cc.core.workspace.workspaces_dir", return_value=tmp_path):
            _invoke(["workspace", "new", "ws-a"])
            _invoke(["workspace", "new", "ws-b", "--description", "Second workspace"])
            result = _invoke(["workspace", "list"])
        assert "ws-a" in result.output
        assert "ws-b" in result.output

    def test_list_workspaces_json(self, tmp_path):
        with patch("zotero_cli_cc.core.workspace.workspaces_dir", return_value=tmp_path):
            _invoke(["workspace", "new", "ws-json"])
            result = _invoke(["workspace", "list"], json_output=True)
        data = json.loads(result.output)
        assert len(data) == 1
        assert data[0]["name"] == "ws-json"

    def test_delete_workspace_with_yes(self, tmp_path):
        with patch("zotero_cli_cc.core.workspace.workspaces_dir", return_value=tmp_path):
            _invoke(["workspace", "new", "doomed"])
            result = _invoke(["workspace", "delete", "doomed", "--yes"])
        assert "Workspace deleted: doomed" in result.output

    def test_delete_workspace_not_found(self, tmp_path):
        with patch("zotero_cli_cc.core.workspace.workspaces_dir", return_value=tmp_path):
            result = _invoke(["workspace", "delete", "nonexistent", "--yes"])
        assert "not found" in result.output

    def test_add_item(self, tmp_path):
        with patch("zotero_cli_cc.core.workspace.workspaces_dir", return_value=tmp_path):
            _invoke(["workspace", "new", "test-ws"])
            result = _invoke(["workspace", "add", "test-ws", "ATTN001"])
        assert result.exit_code == 0
        assert "Added 1 item(s)" in result.output

    def test_add_item_not_found_in_zotero(self, tmp_path):
        with patch("zotero_cli_cc.core.workspace.workspaces_dir", return_value=tmp_path):
            _invoke(["workspace", "new", "test-ws"])
            result = _invoke(["workspace", "add", "test-ws", "NONEXIST"])
        assert "not found in Zotero" in result.output

    def test_add_item_duplicate(self, tmp_path):
        with patch("zotero_cli_cc.core.workspace.workspaces_dir", return_value=tmp_path):
            _invoke(["workspace", "new", "test-ws"])
            _invoke(["workspace", "add", "test-ws", "ATTN001"])
            result = _invoke(["workspace", "add", "test-ws", "ATTN001"])
        assert "already in workspace" in result.output

    def test_add_to_nonexistent_workspace(self, tmp_path):
        with patch("zotero_cli_cc.core.workspace.workspaces_dir", return_value=tmp_path):
            result = _invoke(["workspace", "add", "nope", "ATTN001"])
        assert "not found" in result.output

    def test_remove_item(self, tmp_path):
        with patch("zotero_cli_cc.core.workspace.workspaces_dir", return_value=tmp_path):
            _invoke(["workspace", "new", "test-ws"])
            _invoke(["workspace", "add", "test-ws", "ATTN001"])
            result = _invoke(["workspace", "remove", "test-ws", "ATTN001"])
        assert "Removed 1 item(s)" in result.output

    def test_remove_nonexistent_item(self, tmp_path):
        with patch("zotero_cli_cc.core.workspace.workspaces_dir", return_value=tmp_path):
            _invoke(["workspace", "new", "test-ws"])
            result = _invoke(["workspace", "remove", "test-ws", "NONEXIST"])
        assert "Removed 0 item(s)" in result.output

    def test_show_workspace(self, tmp_path):
        with patch("zotero_cli_cc.core.workspace.workspaces_dir", return_value=tmp_path):
            _invoke(["workspace", "new", "test-ws"])
            _invoke(["workspace", "add", "test-ws", "ATTN001"])
            result = _invoke(["workspace", "show", "test-ws"])
        assert result.exit_code == 0
        assert "ATTN001" in result.output

    def test_show_workspace_json(self, tmp_path):
        with patch("zotero_cli_cc.core.workspace.workspaces_dir", return_value=tmp_path):
            _invoke(["workspace", "new", "test-ws"])
            _invoke(["workspace", "add", "test-ws", "ATTN001"])
            result = _invoke(["workspace", "show", "test-ws"], json_output=True)
        data = json.loads(result.output)
        assert len(data) == 1
        assert data[0]["key"] == "ATTN001"

    def test_show_empty_workspace(self, tmp_path):
        with patch("zotero_cli_cc.core.workspace.workspaces_dir", return_value=tmp_path):
            _invoke(["workspace", "new", "test-ws"])
            result = _invoke(["workspace", "show", "test-ws"])
        assert "empty" in result.output

    def test_show_nonexistent_workspace(self, tmp_path):
        with patch("zotero_cli_cc.core.workspace.workspaces_dir", return_value=tmp_path):
            result = _invoke(["workspace", "show", "nope"])
        assert "not found" in result.output
