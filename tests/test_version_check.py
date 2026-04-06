"""Tests for the version check module."""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

from zotero_cli_cc.core.version_check import _parse_version, check_for_update


class TestParseVersion:
    def test_simple(self):
        assert _parse_version("0.2.3") == (0, 2, 3)

    def test_major(self):
        assert _parse_version("1.0.0") == (1, 0, 0)

    def test_comparison(self):
        assert _parse_version("0.3.0") > _parse_version("0.2.3")
        assert _parse_version("0.2.3") == _parse_version("0.2.3")
        assert _parse_version("0.2.2") < _parse_version("0.2.3")


class TestCheckForUpdate:
    @patch("zotero_cli_cc.core.version_check.urlopen")
    @patch("zotero_cli_cc.core.version_check._CACHE_FILE")
    def test_newer_version_available(self, mock_cache_file, mock_urlopen):
        mock_cache_file.exists.return_value = False
        mock_cache_file.parent = MagicMock()

        resp = MagicMock()
        resp.read.return_value = json.dumps({"info": {"version": "0.3.0"}}).encode()
        resp.__enter__ = MagicMock(return_value=resp)
        resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = resp

        result = check_for_update("0.2.3")
        assert result == "0.3.0"

    @patch("zotero_cli_cc.core.version_check.urlopen")
    @patch("zotero_cli_cc.core.version_check._CACHE_FILE")
    def test_already_latest(self, mock_cache_file, mock_urlopen):
        mock_cache_file.exists.return_value = False
        mock_cache_file.parent = MagicMock()

        resp = MagicMock()
        resp.read.return_value = json.dumps({"info": {"version": "0.2.3"}}).encode()
        resp.__enter__ = MagicMock(return_value=resp)
        resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = resp

        result = check_for_update("0.2.3")
        assert result is None

    @patch("zotero_cli_cc.core.version_check._CACHE_FILE")
    def test_cache_hit_newer(self, mock_cache_file):
        mock_cache_file.exists.return_value = True
        mock_cache_file.read_text.return_value = json.dumps({
            "latest_version": "0.3.0",
            "checked_at": time.time(),
        })

        result = check_for_update("0.2.3")
        assert result == "0.3.0"

    @patch("zotero_cli_cc.core.version_check._CACHE_FILE")
    def test_cache_hit_same(self, mock_cache_file):
        mock_cache_file.exists.return_value = True
        mock_cache_file.read_text.return_value = json.dumps({
            "latest_version": "0.2.3",
            "checked_at": time.time(),
        })

        result = check_for_update("0.2.3")
        assert result is None

    @patch("zotero_cli_cc.core.version_check._CACHE_FILE")
    def test_cache_expired(self, mock_cache_file):
        mock_cache_file.exists.return_value = True
        mock_cache_file.read_text.return_value = json.dumps({
            "latest_version": "0.2.3",
            "checked_at": time.time() - 100000,  # expired
        })
        mock_cache_file.parent = MagicMock()

        with patch("zotero_cli_cc.core.version_check.urlopen") as mock_urlopen:
            resp = MagicMock()
            resp.read.return_value = json.dumps({"info": {"version": "0.3.0"}}).encode()
            resp.__enter__ = MagicMock(return_value=resp)
            resp.__exit__ = MagicMock(return_value=False)
            mock_urlopen.return_value = resp

            result = check_for_update("0.2.3")
            assert result == "0.3.0"

    @patch("zotero_cli_cc.core.version_check.urlopen", side_effect=Exception("network error"))
    @patch("zotero_cli_cc.core.version_check._CACHE_FILE")
    def test_network_error_returns_none(self, mock_cache_file, mock_urlopen):
        mock_cache_file.exists.return_value = False
        mock_cache_file.parent = MagicMock()

        result = check_for_update("0.2.3")
        assert result is None
