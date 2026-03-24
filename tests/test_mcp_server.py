"""Tests for the MCP server tools."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

mcp = pytest.importorskip("mcp", reason="mcp not installed")

from zotero_cli_cc.models import (  # noqa: E402
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

    @patch("zotero_cli_cc.mcp_server._get_reader")
    def test_empty_results(self, mock_get_reader):
        from zotero_cli_cc.mcp_server import _handle_search

        reader = MagicMock()
        reader.search.return_value = SearchResult(items=[], total=0, query="nothing")
        mock_get_reader.return_value = reader

        result = _handle_search("nothing", None, 50)
        assert result["total"] == 0
        assert result["items"] == []

    @patch("zotero_cli_cc.mcp_server._get_reader")
    def test_with_collection_filter(self, mock_get_reader):
        from zotero_cli_cc.mcp_server import _handle_search

        reader = MagicMock()
        reader.search.return_value = SearchResult(items=[], total=0, query="q")
        mock_get_reader.return_value = reader

        _handle_search("q", "MyCol", 10)
        reader.search.assert_called_once_with(
            "q", collection="MyCol", item_type=None, sort=None, direction="desc", limit=10
        )


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
        reader.search.assert_called_once_with(
            "", collection=None, item_type=None, sort=None, direction="desc", limit=50
        )


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

    @patch("zotero_cli_cc.mcp_server._get_reader")
    def test_not_found_raises(self, mock_get_reader):
        from zotero_cli_cc.mcp_server import _handle_read

        reader = MagicMock()
        reader.get_item.return_value = None
        mock_get_reader.return_value = reader

        with pytest.raises(ValueError, match="not found"):
            _handle_read("MISSING")


class TestHandlePdf:
    @patch("zotero_cli_cc.mcp_server.PdfCache")
    @patch("zotero_cli_cc.mcp_server.extract_text_from_pdf")
    @patch("zotero_cli_cc.mcp_server._get_reader")
    @patch("zotero_cli_cc.mcp_server.load_config")
    @patch("zotero_cli_cc.mcp_server.get_data_dir")
    def test_extracts_text(self, mock_data_dir, mock_config, mock_get_reader, mock_extract, mock_cache_cls):
        from zotero_cli_cc.mcp_server import _handle_pdf

        data_dir = Path("/fake/zotero")
        mock_data_dir.return_value = data_dir
        reader = MagicMock()
        att = Attachment(key="ATT1", parent_key="ABC123", filename="paper.pdf", content_type="application/pdf")
        reader.get_pdf_attachment.return_value = att
        mock_get_reader.return_value = reader
        cache = MagicMock()
        cache.get.return_value = None
        mock_cache_cls.return_value = cache
        mock_extract.return_value = "PDF text content"

        with patch.object(Path, "exists", return_value=True):
            result = _handle_pdf("ABC123", None)
        assert result["text"] == "PDF text content"

    @patch("zotero_cli_cc.mcp_server._get_reader")
    @patch("zotero_cli_cc.mcp_server.load_config")
    @patch("zotero_cli_cc.mcp_server.get_data_dir")
    def test_no_pdf_raises(self, mock_data_dir, mock_config, mock_get_reader):
        from zotero_cli_cc.mcp_server import _handle_pdf

        mock_data_dir.return_value = Path("/fake/zotero")
        reader = MagicMock()
        reader.get_pdf_attachment.return_value = None
        mock_get_reader.return_value = reader

        with pytest.raises(ValueError, match="No PDF"):
            _handle_pdf("ABC123", None)


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

    @patch("zotero_cli_cc.mcp_server._get_reader")
    def test_not_found_raises(self, mock_get_reader):
        from zotero_cli_cc.mcp_server import _handle_summarize

        reader = MagicMock()
        reader.get_item.return_value = None
        mock_get_reader.return_value = reader

        with pytest.raises(ValueError, match="not found"):
            _handle_summarize("MISSING")


class TestHandleSummarizeAll:
    @patch("zotero_cli_cc.mcp_server._get_reader")
    def test_returns_all_items(self, mock_get_reader):
        from zotero_cli_cc.mcp_server import _handle_summarize_all

        reader = MagicMock()
        items = [_make_item("K1", "Paper 1"), _make_item("K2", "Paper 2")]
        reader.search.return_value = SearchResult(items=items, total=2, query="")
        mock_get_reader.return_value = reader

        result = _handle_summarize_all(10000)
        assert result["total"] == 2
        assert len(result["items"]) == 2
        assert result["items"][0]["key"] == "K1"
        assert result["items"][0]["abstract"] == "An abstract."


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

    @patch("zotero_cli_cc.mcp_server._get_reader")
    def test_not_found_raises(self, mock_get_reader):
        from zotero_cli_cc.mcp_server import _handle_export

        reader = MagicMock()
        reader.export_citation.return_value = None
        mock_get_reader.return_value = reader

        with pytest.raises(ValueError, match="not found"):
            _handle_export("MISSING", "bibtex")


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

    @patch("zotero_cli_cc.mcp_server._get_reader")
    def test_empty_related(self, mock_get_reader):
        from zotero_cli_cc.mcp_server import _handle_relate

        reader = MagicMock()
        reader.get_related_items.return_value = []
        mock_get_reader.return_value = reader

        result = _handle_relate("ABC123", 20)
        assert result["items"] == []


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

    @patch("zotero_cli_cc.mcp_server._get_reader")
    def test_empty_notes(self, mock_get_reader):
        from zotero_cli_cc.mcp_server import _handle_note_view

        reader = MagicMock()
        reader.get_notes.return_value = []
        mock_get_reader.return_value = reader

        result = _handle_note_view("ABC123")
        assert result["notes"] == []


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

    @patch("zotero_cli_cc.mcp_server._get_reader")
    def test_not_found_raises(self, mock_get_reader):
        from zotero_cli_cc.mcp_server import _handle_tag_view

        reader = MagicMock()
        reader.get_item.return_value = None
        mock_get_reader.return_value = reader

        with pytest.raises(ValueError, match="not found"):
            _handle_tag_view("MISSING")


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

    @patch("zotero_cli_cc.mcp_server._get_reader")
    def test_empty_collection(self, mock_get_reader):
        from zotero_cli_cc.mcp_server import _handle_collection_items

        reader = MagicMock()
        reader.get_collection_items.return_value = []
        mock_get_reader.return_value = reader

        result = _handle_collection_items("EMPTY")
        assert result["items"] == []


# ---------------------------------------------------------------------------
# Error propagation
# ---------------------------------------------------------------------------


class TestErrorPropagation:
    """Ensure errors from reader methods propagate to callers."""

    @patch("zotero_cli_cc.mcp_server._get_reader")
    def test_read_propagates_error(self, mock_get_reader):
        from zotero_cli_cc.mcp_server import _handle_read

        reader = MagicMock()
        reader.get_item.side_effect = RuntimeError("db error")
        mock_get_reader.return_value = reader

        with pytest.raises(RuntimeError):
            _handle_read("ABC123")

    @patch("zotero_cli_cc.mcp_server._get_reader")
    def test_search_propagates_error(self, mock_get_reader):
        from zotero_cli_cc.mcp_server import _handle_search

        reader = MagicMock()
        reader.search.side_effect = RuntimeError("db error")
        mock_get_reader.return_value = reader

        with pytest.raises(RuntimeError):
            _handle_search("q", None, 50)


# ---------------------------------------------------------------------------
# Write tool handler tests
# ---------------------------------------------------------------------------


class TestGetWriter:
    @patch("zotero_cli_cc.mcp_server.load_config")
    def test_returns_writer_when_credentials(self, mock_config):
        from zotero_cli_cc.mcp_server import _get_writer

        cfg = MagicMock()
        cfg.has_write_credentials = True
        cfg.library_id = "12345"
        cfg.api_key = "secret"
        mock_config.return_value = cfg

        with patch("zotero_cli_cc.mcp_server.ZoteroWriter") as mock_writer_cls:
            mock_writer_cls.return_value = MagicMock()
            _get_writer()
            mock_writer_cls.assert_called_once_with("12345", "secret", library_type="user")

    @patch("zotero_cli_cc.mcp_server.load_config")
    def test_raises_without_credentials(self, mock_config):
        from zotero_cli_cc.mcp_server import _get_writer

        cfg = MagicMock()
        cfg.has_write_credentials = False
        mock_config.return_value = cfg

        with pytest.raises(ValueError, match="credentials"):
            _get_writer()


class TestHandleNoteAdd:
    @patch("zotero_cli_cc.mcp_server._get_writer")
    def test_adds_note(self, mock_get_writer):
        from zotero_cli_cc.mcp_server import _handle_note_add

        writer = MagicMock()
        writer.add_note.return_value = "NOTE2"
        mock_get_writer.return_value = writer

        result = _handle_note_add("ABC123", "Some note content")
        assert result["note_key"] == "NOTE2"
        writer.add_note.assert_called_once_with("ABC123", "Some note content")


class TestHandleNoteUpdate:
    @patch("zotero_cli_cc.mcp_server._get_writer")
    def test_updates_note(self, mock_get_writer):
        from zotero_cli_cc.mcp_server import _handle_note_update

        writer = MagicMock()
        mock_get_writer.return_value = writer

        result = _handle_note_update("NOTE1", "Updated content")
        assert result["note_key"] == "NOTE1"
        assert result["updated"] is True
        writer.update_note.assert_called_once_with("NOTE1", "Updated content")


class TestHandleTagAdd:
    @patch("zotero_cli_cc.mcp_server._get_writer")
    def test_adds_tags(self, mock_get_writer):
        from zotero_cli_cc.mcp_server import _handle_tag_add

        writer = MagicMock()
        mock_get_writer.return_value = writer

        result = _handle_tag_add(["ABC123"], ["ML", "NLP"])
        assert result["results"][0]["key"] == "ABC123"
        assert result["results"][0]["tags_added"] == ["ML", "NLP"]
        writer.add_tags.assert_called_once_with("ABC123", ["ML", "NLP"])

    @patch("zotero_cli_cc.mcp_server._get_writer")
    def test_adds_tags_batch(self, mock_get_writer):
        from zotero_cli_cc.mcp_server import _handle_tag_add

        writer = MagicMock()
        mock_get_writer.return_value = writer

        result = _handle_tag_add(["K1", "K2"], ["ML"])
        assert len(result["results"]) == 2
        assert writer.add_tags.call_count == 2


class TestHandleTagRemove:
    @patch("zotero_cli_cc.mcp_server._get_writer")
    def test_removes_tags(self, mock_get_writer):
        from zotero_cli_cc.mcp_server import _handle_tag_remove

        writer = MagicMock()
        mock_get_writer.return_value = writer

        result = _handle_tag_remove(["ABC123"], ["ML"])
        assert result["results"][0]["key"] == "ABC123"
        assert result["results"][0]["tags_removed"] == ["ML"]
        writer.remove_tags.assert_called_once_with("ABC123", ["ML"])


class TestHandleAdd:
    @patch("zotero_cli_cc.mcp_server._get_writer")
    def test_add_by_doi(self, mock_get_writer):
        from zotero_cli_cc.mcp_server import _handle_add

        writer = MagicMock()
        writer.add_item.return_value = "NEW1"
        mock_get_writer.return_value = writer

        result = _handle_add("10.1234/test", None)
        assert result["item_key"] == "NEW1"
        writer.add_item.assert_called_once_with(doi="10.1234/test", url=None)

    @patch("zotero_cli_cc.mcp_server._get_writer")
    def test_add_by_url(self, mock_get_writer):
        from zotero_cli_cc.mcp_server import _handle_add

        writer = MagicMock()
        writer.add_item.return_value = "NEW2"
        mock_get_writer.return_value = writer

        result = _handle_add(None, "https://example.com/paper")
        assert result["item_key"] == "NEW2"
        writer.add_item.assert_called_once_with(doi=None, url="https://example.com/paper")

    def test_raises_without_doi_or_url(self):
        from zotero_cli_cc.mcp_server import _handle_add

        with pytest.raises(ValueError, match="Either doi or url"):
            _handle_add(None, None)


class TestHandleDelete:
    @patch("zotero_cli_cc.mcp_server._get_writer")
    def test_deletes_item(self, mock_get_writer):
        from zotero_cli_cc.mcp_server import _handle_delete

        writer = MagicMock()
        mock_get_writer.return_value = writer

        result = _handle_delete(["ABC123"])
        assert result["results"][0]["deleted"] is True
        assert result["results"][0]["key"] == "ABC123"
        writer.delete_item.assert_called_once_with("ABC123")

    @patch("zotero_cli_cc.mcp_server._get_writer")
    def test_deletes_batch(self, mock_get_writer):
        from zotero_cli_cc.mcp_server import _handle_delete

        writer = MagicMock()
        mock_get_writer.return_value = writer

        result = _handle_delete(["K1", "K2", "K3"])
        assert len(result["results"]) == 3
        assert writer.delete_item.call_count == 3


class TestHandleCollectionCreate:
    @patch("zotero_cli_cc.mcp_server._get_writer")
    def test_creates_collection(self, mock_get_writer):
        from zotero_cli_cc.mcp_server import _handle_collection_create

        writer = MagicMock()
        writer.create_collection.return_value = "COL2"
        mock_get_writer.return_value = writer

        result = _handle_collection_create("New Collection", None)
        assert result["collection_key"] == "COL2"
        writer.create_collection.assert_called_once_with("New Collection", parent_key=None)

    @patch("zotero_cli_cc.mcp_server._get_writer")
    def test_creates_subcollection(self, mock_get_writer):
        from zotero_cli_cc.mcp_server import _handle_collection_create

        writer = MagicMock()
        writer.create_collection.return_value = "COL3"
        mock_get_writer.return_value = writer

        result = _handle_collection_create("Sub Collection", "COL1")
        assert result["collection_key"] == "COL3"
        writer.create_collection.assert_called_once_with("Sub Collection", parent_key="COL1")


class TestHandleCollectionMove:
    @patch("zotero_cli_cc.mcp_server._get_writer")
    def test_moves_item(self, mock_get_writer):
        from zotero_cli_cc.mcp_server import _handle_collection_move

        writer = MagicMock()
        mock_get_writer.return_value = writer

        result = _handle_collection_move("ITEM1", "COL1")
        assert result["item_key"] == "ITEM1"
        assert result["collection_key"] == "COL1"
        writer.move_to_collection.assert_called_once_with("ITEM1", "COL1")


class TestHandleCollectionDelete:
    @patch("zotero_cli_cc.mcp_server._get_writer")
    def test_deletes_collection(self, mock_get_writer):
        from zotero_cli_cc.mcp_server import _handle_collection_delete

        writer = MagicMock()
        mock_get_writer.return_value = writer

        result = _handle_collection_delete("COL1")
        assert result["deleted"] is True
        assert result["collection_key"] == "COL1"
        writer.delete_collection.assert_called_once_with("COL1")


class TestHandleCollectionRename:
    @patch("zotero_cli_cc.mcp_server._get_writer")
    def test_renames_collection(self, mock_get_writer):
        from zotero_cli_cc.mcp_server import _handle_collection_rename

        writer = MagicMock()
        mock_get_writer.return_value = writer

        result = _handle_collection_rename("COL1", "New Name")
        assert result["collection_key"] == "COL1"
        assert result["new_name"] == "New Name"
        writer.rename_collection.assert_called_once_with("COL1", "New Name")


class TestHandleCollectionReorganize:
    @patch("zotero_cli_cc.mcp_server._get_writer")
    def test_creates_collections_and_moves_items(self, mock_get_writer):
        from zotero_cli_cc.mcp_server import _handle_collection_reorganize

        writer = MagicMock()
        writer.create_collection.side_effect = ["COL_A", "COL_B"]
        mock_get_writer.return_value = writer

        plan = {
            "collections": [
                {"name": "Topic A", "items": ["K1", "K2"]},
                {"name": "Topic B", "items": ["K3"]},
            ]
        }
        result = _handle_collection_reorganize(plan)
        assert result["collections_created"] == 2
        assert len(result["results"]) == 2
        assert result["results"][0]["items_moved"] == 2
        assert result["results"][1]["items_moved"] == 1
        assert writer.create_collection.call_count == 2
        assert writer.move_to_collection.call_count == 3

    @patch("zotero_cli_cc.mcp_server._get_writer")
    def test_with_parent_collections(self, mock_get_writer):
        from zotero_cli_cc.mcp_server import _handle_collection_reorganize

        writer = MagicMock()
        writer.create_collection.side_effect = ["PARENT1", "CHILD1"]
        mock_get_writer.return_value = writer

        plan = {
            "collections": [
                {"name": "ML", "items": []},
                {"name": "RL", "parent": "ML", "items": ["K1"]},
            ]
        }
        result = _handle_collection_reorganize(plan)
        assert result["collections_created"] == 2
        # Second create_collection should use PARENT1 as parent_key
        calls = writer.create_collection.call_args_list
        assert calls[1] == (("RL",), {"parent_key": "PARENT1"})

    @patch("zotero_cli_cc.mcp_server._get_writer")
    def test_empty_plan_raises(self, mock_get_writer):
        from zotero_cli_cc.mcp_server import _handle_collection_reorganize

        mock_get_writer.return_value = MagicMock()
        with pytest.raises(ValueError, match="No collections"):
            _handle_collection_reorganize({"collections": []})


# ---------------------------------------------------------------------------
# Write error handling tests
# ---------------------------------------------------------------------------


class TestMcpWriteErrorHandling:
    """Verify that ZoteroWriteError is caught and returned as structured dicts."""

    @pytest.fixture(autouse=True)
    def mock_get_writer(self):
        from zotero_cli_cc.core.writer import ZoteroWriteError

        writer = MagicMock()
        with patch("zotero_cli_cc.mcp_server._get_writer", return_value=writer):
            self.writer = writer
            self.ZoteroWriteError = ZoteroWriteError
            yield

    def test_note_add_error(self):
        from zotero_cli_cc.mcp_server import _handle_note_add

        self.writer.add_note.side_effect = self.ZoteroWriteError("Item not found")
        result = _handle_note_add("K1", "text")
        assert result["error"] == "Item not found"
        assert result["context"] == "note_add"

    def test_note_update_error(self):
        from zotero_cli_cc.mcp_server import _handle_note_update

        self.writer.update_note.side_effect = self.ZoteroWriteError("Note not found")
        result = _handle_note_update("N1", "text")
        assert result["error"] == "Note not found"
        assert result["context"] == "note_update"

    def test_tag_add_error(self):
        from zotero_cli_cc.mcp_server import _handle_tag_add

        self.writer.add_tags.side_effect = self.ZoteroWriteError("Network error")
        result = _handle_tag_add(["K1"], ["t1"])
        assert result["results"][0]["error"] == "Network error"

    def test_tag_remove_error(self):
        from zotero_cli_cc.mcp_server import _handle_tag_remove

        self.writer.remove_tags.side_effect = self.ZoteroWriteError("Item not found")
        result = _handle_tag_remove(["K1"], ["t1"])
        assert result["results"][0]["error"] == "Item not found"

    def test_add_error(self):
        from zotero_cli_cc.mcp_server import _handle_add

        self.writer.add_item.side_effect = self.ZoteroWriteError("API error: Bad request")
        result = _handle_add(doi="10.1234/test", url=None)
        assert result["error"] == "API error: Bad request"
        assert result["context"] == "add"

    def test_delete_error(self):
        from zotero_cli_cc.mcp_server import _handle_delete

        self.writer.delete_item.side_effect = self.ZoteroWriteError("Item 'K1' not found")
        result = _handle_delete(["K1"])
        assert result["results"][0]["error"] == "Item 'K1' not found"
        assert result["results"][0]["deleted"] is False

    def test_collection_create_error(self):
        from zotero_cli_cc.mcp_server import _handle_collection_create

        self.writer.create_collection.side_effect = self.ZoteroWriteError("Network error")
        result = _handle_collection_create("Test", None)
        assert result["error"] == "Network error"

    def test_collection_move_error(self):
        from zotero_cli_cc.mcp_server import _handle_collection_move

        self.writer.move_to_collection.side_effect = self.ZoteroWriteError("Not found")
        result = _handle_collection_move("K1", "COL1")
        assert result["error"] == "Not found"

    def test_collection_delete_error(self):
        from zotero_cli_cc.mcp_server import _handle_collection_delete

        self.writer.delete_collection.side_effect = self.ZoteroWriteError("Not found")
        result = _handle_collection_delete("COL1")
        assert result["error"] == "Not found"

    def test_collection_rename_error(self):
        from zotero_cli_cc.mcp_server import _handle_collection_rename

        self.writer.rename_collection.side_effect = self.ZoteroWriteError("Not found")
        result = _handle_collection_rename("COL1", "New")
        assert result["error"] == "Not found"
