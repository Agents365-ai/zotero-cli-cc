"""Tests for the MCP server read-only tools."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from zotero_cli_cc.models import (
    Attachment,
    Collection,
    Creator,
    Item,
    Note,
    SearchResult,
)


def _make_item(key: str = "ABC123", title: str = "Test Paper") -> Item:
    return Item(
        key=key,
        item_type="journalArticle",
        title=title,
        creators=[Creator("Jane", "Doe", "author")],
        abstract="An abstract.",
        date="2024",
        url="https://example.com",
        doi="10.1234/test",
        tags=["ML", "AI"],
        collections=["COL1"],
        date_added="2024-01-01",
        date_modified="2024-06-01",
    )


def _make_note(key: str = "NOTE1", parent_key: str = "ABC123") -> Note:
    return Note(key=key, parent_key=parent_key, content="Some note content.", tags=["review"])


def _make_collection(key: str = "COL1", name: str = "My Collection") -> Collection:
    return Collection(key=key, name=name, parent_key=None, children=[])


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------


class TestItemToDict:
    def test_standard(self):
        from zotero_cli_cc.mcp_server import _item_to_dict

        item = _make_item()
        d = _item_to_dict(item)
        assert d["key"] == "ABC123"
        assert d["title"] == "Test Paper"
        assert d["authors"] == ["Jane Doe"]
        assert d["tags"] == ["ML", "AI"]
        assert d["doi"] == "10.1234/test"

    def test_minimal(self):
        from zotero_cli_cc.mcp_server import _item_to_dict

        item = _make_item()
        d = _item_to_dict(item, detail="minimal")
        assert d["key"] == "ABC123"
        assert d["title"] == "Test Paper"
        assert "abstract" not in d
        assert "tags" not in d
        assert "doi" not in d

    def test_full(self):
        from zotero_cli_cc.mcp_server import _item_to_dict

        item = _make_item()
        item.extra = {"publication": "Nature"}
        d = _item_to_dict(item, detail="full")
        assert d["extra"] == {"publication": "Nature"}
        assert d["tags"] == ["ML", "AI"]


class TestNoteToDict:
    def test_basic(self):
        from zotero_cli_cc.mcp_server import _note_to_dict

        note = _make_note()
        d = _note_to_dict(note)
        assert d["key"] == "NOTE1"
        assert d["parent_key"] == "ABC123"
        assert d["content"] == "Some note content."
        assert d["tags"] == ["review"]


class TestCollectionToDict:
    def test_basic(self):
        from zotero_cli_cc.mcp_server import _collection_to_dict

        child = Collection(key="CHILD1", name="Sub", parent_key="COL1", children=[])
        coll = Collection(key="COL1", name="My Collection", parent_key=None, children=[child])
        d = _collection_to_dict(coll)
        assert d["key"] == "COL1"
        assert d["name"] == "My Collection"
        assert len(d["children"]) == 1
        assert d["children"][0]["key"] == "CHILD1"


# ---------------------------------------------------------------------------
# Handler tests
# ---------------------------------------------------------------------------


class TestHandleSearch:
    @patch("zotero_cli_cc.mcp_server._get_reader")
    def test_returns_results(self, mock_get_reader):
        from zotero_cli_cc.mcp_server import _handle_search

        reader = MagicMock()
        item = _make_item()
        reader.search.return_value = SearchResult(items=[item], total=1, query="test")
        mock_get_reader.return_value = reader

        result = _handle_search("test", None, 50)
        assert result["total"] == 1
        assert result["query"] == "test"
        assert len(result["items"]) == 1
        assert result["items"][0]["key"] == "ABC123"
        reader.close.assert_called_once()

    @patch("zotero_cli_cc.mcp_server._get_reader")
    def test_empty_results(self, mock_get_reader):
        from zotero_cli_cc.mcp_server import _handle_search

        reader = MagicMock()
        reader.search.return_value = SearchResult(items=[], total=0, query="nothing")
        mock_get_reader.return_value = reader

        result = _handle_search("nothing", None, 50)
        assert result["total"] == 0
        assert result["items"] == []
        reader.close.assert_called_once()

    @patch("zotero_cli_cc.mcp_server._get_reader")
    def test_with_collection_filter(self, mock_get_reader):
        from zotero_cli_cc.mcp_server import _handle_search

        reader = MagicMock()
        reader.search.return_value = SearchResult(items=[], total=0, query="q")
        mock_get_reader.return_value = reader

        _handle_search("q", "MyCol", 10)
        reader.search.assert_called_once_with("q", collection="MyCol", limit=10)
        reader.close.assert_called_once()


class TestHandleListItems:
    @patch("zotero_cli_cc.mcp_server._get_reader")
    def test_returns_items(self, mock_get_reader):
        from zotero_cli_cc.mcp_server import _handle_list_items

        reader = MagicMock()
        item = _make_item()
        reader.search.return_value = SearchResult(items=[item], total=1, query="")
        mock_get_reader.return_value = reader

        result = _handle_list_items(50)
        assert result["total"] == 1
        assert len(result["items"]) == 1
        reader.search.assert_called_once_with("", collection=None, limit=50)
        reader.close.assert_called_once()


class TestHandleRead:
    @patch("zotero_cli_cc.mcp_server._get_reader")
    def test_found(self, mock_get_reader):
        from zotero_cli_cc.mcp_server import _handle_read

        reader = MagicMock()
        item = _make_item()
        reader.get_item.return_value = item
        reader.get_notes.return_value = [_make_note()]
        mock_get_reader.return_value = reader

        result = _handle_read("ABC123")
        assert result["item"]["key"] == "ABC123"
        assert len(result["notes"]) == 1
        reader.close.assert_called_once()

    @patch("zotero_cli_cc.mcp_server._get_reader")
    def test_not_found_raises(self, mock_get_reader):
        from zotero_cli_cc.mcp_server import _handle_read

        reader = MagicMock()
        reader.get_item.return_value = None
        mock_get_reader.return_value = reader

        with pytest.raises(ValueError, match="not found"):
            _handle_read("MISSING")
        reader.close.assert_called_once()


class TestHandlePdf:
    @patch("zotero_cli_cc.mcp_server.PdfCache")
    @patch("zotero_cli_cc.mcp_server.extract_text_from_pdf")
    @patch("zotero_cli_cc.mcp_server.ZoteroReader")
    @patch("zotero_cli_cc.mcp_server.load_config")
    @patch("zotero_cli_cc.mcp_server.get_data_dir")
    def test_extracts_text(self, mock_data_dir, mock_config, mock_reader_cls, mock_extract, mock_cache_cls):
        from zotero_cli_cc.mcp_server import _handle_pdf

        data_dir = Path("/fake/zotero")
        mock_data_dir.return_value = data_dir
        reader = MagicMock()
        att = Attachment(key="ATT1", parent_key="ABC123", filename="paper.pdf", content_type="application/pdf")
        reader.get_pdf_attachment.return_value = att
        mock_reader_cls.return_value = reader
        cache = MagicMock()
        cache.get.return_value = None
        mock_cache_cls.return_value = cache
        mock_extract.return_value = "PDF text content"

        pdf_path = data_dir / "storage" / "ATT1" / "paper.pdf"
        with patch.object(Path, "exists", return_value=True):
            result = _handle_pdf("ABC123", None)
        assert result["text"] == "PDF text content"
        reader.close.assert_called_once()

    @patch("zotero_cli_cc.mcp_server.ZoteroReader")
    @patch("zotero_cli_cc.mcp_server.load_config")
    @patch("zotero_cli_cc.mcp_server.get_data_dir")
    def test_no_pdf_raises(self, mock_data_dir, mock_config, mock_reader_cls):
        from zotero_cli_cc.mcp_server import _handle_pdf

        mock_data_dir.return_value = Path("/fake/zotero")
        reader = MagicMock()
        reader.get_pdf_attachment.return_value = None
        mock_reader_cls.return_value = reader

        with pytest.raises(ValueError, match="No PDF"):
            _handle_pdf("ABC123", None)
        reader.close.assert_called_once()


class TestHandleSummarize:
    @patch("zotero_cli_cc.mcp_server._get_reader")
    def test_returns_summary(self, mock_get_reader):
        from zotero_cli_cc.mcp_server import _handle_summarize

        reader = MagicMock()
        item = _make_item()
        reader.get_item.return_value = item
        reader.get_notes.return_value = [_make_note()]
        mock_get_reader.return_value = reader

        result = _handle_summarize("ABC123")
        assert result["title"] == "Test Paper"
        assert result["authors"] == ["Jane Doe"]
        assert result["year"] == "2024"
        assert result["doi"] == "10.1234/test"
        assert result["abstract"] == "An abstract."
        assert len(result["notes"]) == 1
        reader.close.assert_called_once()

    @patch("zotero_cli_cc.mcp_server._get_reader")
    def test_not_found_raises(self, mock_get_reader):
        from zotero_cli_cc.mcp_server import _handle_summarize

        reader = MagicMock()
        reader.get_item.return_value = None
        mock_get_reader.return_value = reader

        with pytest.raises(ValueError, match="not found"):
            _handle_summarize("MISSING")
        reader.close.assert_called_once()


class TestHandleExport:
    @patch("zotero_cli_cc.mcp_server._get_reader")
    def test_returns_citation(self, mock_get_reader):
        from zotero_cli_cc.mcp_server import _handle_export

        reader = MagicMock()
        reader.export_citation.return_value = "@article{abc, title={Test}}"
        mock_get_reader.return_value = reader

        result = _handle_export("ABC123", "bibtex")
        assert result["citation"] == "@article{abc, title={Test}}"
        assert result["format"] == "bibtex"
        reader.close.assert_called_once()

    @patch("zotero_cli_cc.mcp_server._get_reader")
    def test_not_found_raises(self, mock_get_reader):
        from zotero_cli_cc.mcp_server import _handle_export

        reader = MagicMock()
        reader.export_citation.return_value = None
        mock_get_reader.return_value = reader

        with pytest.raises(ValueError, match="not found"):
            _handle_export("MISSING", "bibtex")
        reader.close.assert_called_once()


class TestHandleRelate:
    @patch("zotero_cli_cc.mcp_server._get_reader")
    def test_returns_related(self, mock_get_reader):
        from zotero_cli_cc.mcp_server import _handle_relate

        reader = MagicMock()
        related = [_make_item("REL1", "Related Paper")]
        reader.get_related_items.return_value = related
        mock_get_reader.return_value = reader

        result = _handle_relate("ABC123", 20)
        assert len(result["items"]) == 1
        assert result["items"][0]["key"] == "REL1"
        assert result["source_key"] == "ABC123"
        reader.close.assert_called_once()

    @patch("zotero_cli_cc.mcp_server._get_reader")
    def test_empty_related(self, mock_get_reader):
        from zotero_cli_cc.mcp_server import _handle_relate

        reader = MagicMock()
        reader.get_related_items.return_value = []
        mock_get_reader.return_value = reader

        result = _handle_relate("ABC123", 20)
        assert result["items"] == []
        reader.close.assert_called_once()


class TestHandleNoteView:
    @patch("zotero_cli_cc.mcp_server._get_reader")
    def test_returns_notes(self, mock_get_reader):
        from zotero_cli_cc.mcp_server import _handle_note_view

        reader = MagicMock()
        reader.get_notes.return_value = [_make_note()]
        mock_get_reader.return_value = reader

        result = _handle_note_view("ABC123")
        assert len(result["notes"]) == 1
        assert result["notes"][0]["content"] == "Some note content."
        assert result["parent_key"] == "ABC123"
        reader.close.assert_called_once()

    @patch("zotero_cli_cc.mcp_server._get_reader")
    def test_empty_notes(self, mock_get_reader):
        from zotero_cli_cc.mcp_server import _handle_note_view

        reader = MagicMock()
        reader.get_notes.return_value = []
        mock_get_reader.return_value = reader

        result = _handle_note_view("ABC123")
        assert result["notes"] == []
        reader.close.assert_called_once()


class TestHandleTagView:
    @patch("zotero_cli_cc.mcp_server._get_reader")
    def test_returns_tags(self, mock_get_reader):
        from zotero_cli_cc.mcp_server import _handle_tag_view

        reader = MagicMock()
        item = _make_item()
        reader.get_item.return_value = item
        mock_get_reader.return_value = reader

        result = _handle_tag_view("ABC123")
        assert result["tags"] == ["ML", "AI"]
        assert result["key"] == "ABC123"
        reader.close.assert_called_once()

    @patch("zotero_cli_cc.mcp_server._get_reader")
    def test_not_found_raises(self, mock_get_reader):
        from zotero_cli_cc.mcp_server import _handle_tag_view

        reader = MagicMock()
        reader.get_item.return_value = None
        mock_get_reader.return_value = reader

        with pytest.raises(ValueError, match="not found"):
            _handle_tag_view("MISSING")
        reader.close.assert_called_once()


class TestHandleCollectionList:
    @patch("zotero_cli_cc.mcp_server._get_reader")
    def test_returns_collections(self, mock_get_reader):
        from zotero_cli_cc.mcp_server import _handle_collection_list

        reader = MagicMock()
        reader.get_collections.return_value = [_make_collection()]
        mock_get_reader.return_value = reader

        result = _handle_collection_list()
        assert len(result["collections"]) == 1
        assert result["collections"][0]["name"] == "My Collection"
        reader.close.assert_called_once()


class TestHandleCollectionItems:
    @patch("zotero_cli_cc.mcp_server._get_reader")
    def test_returns_items(self, mock_get_reader):
        from zotero_cli_cc.mcp_server import _handle_collection_items

        reader = MagicMock()
        reader.get_collection_items.return_value = [_make_item()]
        mock_get_reader.return_value = reader

        result = _handle_collection_items("COL1")
        assert len(result["items"]) == 1
        assert result["collection_key"] == "COL1"
        reader.close.assert_called_once()

    @patch("zotero_cli_cc.mcp_server._get_reader")
    def test_empty_collection(self, mock_get_reader):
        from zotero_cli_cc.mcp_server import _handle_collection_items

        reader = MagicMock()
        reader.get_collection_items.return_value = []
        mock_get_reader.return_value = reader

        result = _handle_collection_items("EMPTY")
        assert result["items"] == []
        reader.close.assert_called_once()


# ---------------------------------------------------------------------------
# Reader close on error
# ---------------------------------------------------------------------------


class TestReaderAlwaysClosed:
    """Ensure reader.close() is called even when handlers raise."""

    @patch("zotero_cli_cc.mcp_server._get_reader")
    def test_read_closes_on_error(self, mock_get_reader):
        from zotero_cli_cc.mcp_server import _handle_read

        reader = MagicMock()
        reader.get_item.side_effect = RuntimeError("db error")
        mock_get_reader.return_value = reader

        with pytest.raises(RuntimeError):
            _handle_read("ABC123")
        reader.close.assert_called_once()

    @patch("zotero_cli_cc.mcp_server._get_reader")
    def test_search_closes_on_error(self, mock_get_reader):
        from zotero_cli_cc.mcp_server import _handle_search

        reader = MagicMock()
        reader.search.side_effect = RuntimeError("db error")
        mock_get_reader.return_value = reader

        with pytest.raises(RuntimeError):
            _handle_search("q", None, 50)
        reader.close.assert_called_once()
