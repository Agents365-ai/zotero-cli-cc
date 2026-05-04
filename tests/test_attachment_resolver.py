import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
import tempfile
import os

from zotero_cli_cc.core.attachment_resolver import AttachmentResolver


class TestAttachmentResolver:
    def test_resolve_storage_path(self, tmp_path):
        """'storage:file.pdf' resolves to <storage_dir>/<key>/file.pdf."""
        storage = tmp_path / "storage"
        storage.mkdir()
        (storage / "ABC123").mkdir()
        db_path = tmp_path / "zotero.sqlite"
        db_path.touch()

        resolver = AttachmentResolver(db_path)
        result = resolver.resolve("ABC123", "storage:paper.pdf")
        assert result == storage / "ABC123" / "paper.pdf"

    def test_resolve_storage_with_subdir(self, tmp_path):
        """'storage:key/subdir/file.pdf' resolves correctly."""
        storage = tmp_path / "storage"
        storage.mkdir()
        (storage / "ABC123").mkdir()
        db_path = tmp_path / "zotero.sqlite"
        db_path.touch()

        resolver = AttachmentResolver(db_path)
        result = resolver.resolve("ABC123", "storage:subdir/paper.pdf")
        assert result == storage / "ABC123" / "subdir" / "paper.pdf"

    def test_resolve_file_url_unix(self, tmp_path):
        """'file:///path/to/file.pdf' resolves to /path/to/file.pdf."""
        db_path = tmp_path / "zotero.sqlite"
        db_path.touch()

        resolver = AttachmentResolver(db_path)
        result = resolver.resolve("ABC123", "file:///home/user/papers/file.pdf")
        assert result == Path("/home/user/papers/file.pdf")

    def test_resolve_file_url_encoded_spaces(self, tmp_path):
        """'file:///path/to/my%20file.pdf' resolves to path with spaces."""
        db_path = tmp_path / "zotero.sqlite"
        db_path.touch()

        resolver = AttachmentResolver(db_path)
        result = resolver.resolve("ABC123", "file:///home/user/my%20file.pdf")
        assert result == Path("/home/user/my file.pdf")

    def test_resolve_file_url_windows_drive(self, tmp_path):
        """'file:///C:/Users/test/file.pdf' resolves to C:/Users/test/file.pdf."""
        db_path = tmp_path / "zotero.sqlite"
        db_path.touch()

        resolver = AttachmentResolver(db_path)
        with patch("os.name", "nt"), patch("zotero_cli_cc.core.attachment_resolver.is_wsl_environment", return_value=False):
            result = resolver.resolve("ABC123", "file:///C:/Users/test/file.pdf")
        # On Windows, Path normalizes / to \; on Linux (where os.name is patched but Path
        # still uses PosixPath), forward slashes are preserved.
        assert str(result).replace("\\", "/") == "C:/Users/test/file.pdf"

    def test_resolve_absolute_path_unix(self, tmp_path):
        """'/absolute/path/to/file.pdf' used as-is."""
        db_path = tmp_path / "zotero.sqlite"
        db_path.touch()

        resolver = AttachmentResolver(db_path)
        result = resolver.resolve("ABC123", "/home/user/papers/file.pdf")
        assert result == Path("/home/user/papers/file.pdf")

    def test_resolve_attachments_with_prefs(self, tmp_path):
        """'attachments:relative/path.pdf' resolved against prefs.js base path."""
        storage = tmp_path / "storage"
        storage.mkdir()
        db_path = tmp_path / "zotero.sqlite"
        db_path.touch()
        attach_base = tmp_path / "attachments_base"
        attach_base.mkdir()
        prefs = tmp_path / "prefs.js"
        prefs.write_text(f'user_pref("extensions.zotero.baseAttachmentPath", "{attach_base}");')

        resolver = AttachmentResolver(db_path)
        with patch("zotero_cli_cc.core.attachment_resolver.is_wsl_environment", return_value=False):
            result = resolver.resolve("ABC123", "attachments:papers/file.pdf")
        assert result == attach_base / "papers" / "file.pdf"

    def test_resolve_attachments_fallback_to_data_dir(self, tmp_path):
        storage = tmp_path / "storage"
        storage.mkdir()
        db_path = tmp_path / "zotero.sqlite"
        db_path.touch()

        resolver = AttachmentResolver(db_path)
        with patch("glob.glob", return_value=[]):
            result = resolver.resolve("ABC123", "attachments:papers/file.pdf")
        assert result == tmp_path / "papers" / "file.pdf"

    def test_resolve_empty_path(self, tmp_path):
        """Empty path returns None."""
        db_path = tmp_path / "zotero.sqlite"
        db_path.touch()

        resolver = AttachmentResolver(db_path)
        result = resolver.resolve("ABC123", "")
        assert result is None

    def test_resolve_unknown_prefix(self, tmp_path):
        """Unknown prefix returns None."""
        db_path = tmp_path / "zotero.sqlite"
        db_path.touch()

        resolver = AttachmentResolver(db_path)
        result = resolver.resolve("ABC123", "ftp://server/file.pdf")
        assert result is None

    def test_storage_dir_property(self, tmp_path):
        """storage_dir is db_path.parent / 'storage'."""
        db_path = tmp_path / "zotero.sqlite"
        db_path.touch()

        resolver = AttachmentResolver(db_path)
        assert resolver.storage_dir == tmp_path / "storage"