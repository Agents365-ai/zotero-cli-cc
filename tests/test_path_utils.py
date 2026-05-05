"""Tests for the path_utils module."""

from __future__ import annotations

from unittest.mock import mock_open, patch

from zotero_cli_cc.core.path_utils import (
    is_wsl_environment,
    windows_to_wsl_path,
)


class TestWindowsToWslPath:
    def test_windows_to_wsl_path_drive_letter(self):
        result = windows_to_wsl_path(r"C:\Users\test\file.pdf")
        assert result == "/mnt/c/Users/test/file.pdf"

    def test_windows_to_wsl_path_unc(self):
        result = windows_to_wsl_path(r"\\server\share\file.pdf")
        assert result == "/mnt/server/share/file.pdf"

    def test_windows_to_wsl_path_already_wsl(self):
        result = windows_to_wsl_path("/mnt/c/already/wsl.pdf")
        assert result == "/mnt/c/already/wsl.pdf"

    def test_windows_to_wsl_path_empty(self):
        result = windows_to_wsl_path("")
        assert result == ""


class TestIsWslEnvironment:
    def test_is_wsl_environment_true(self):
        with patch(
            "builtins.open",
            mock_open(read_data="microsoft wsl 5.15.0\n"),
        ):
            result = is_wsl_environment()
            assert result is True

    def test_is_wsl_environment_false(self):
        with patch(
            "builtins.open",
            mock_open(read_data="Linux version 5.15.0\n"),
        ):
            result = is_wsl_environment()
            assert result is False

    def test_is_wsl_environment_error(self):
        with patch("builtins.open", side_effect=OSError("No such file")):
            result = is_wsl_environment()
            assert result is False
