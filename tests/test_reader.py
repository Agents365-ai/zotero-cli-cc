import pytest
from pathlib import Path

from zotero_cli_cc.core.reader import ZoteroReader
from zotero_cli_cc.models import Item, Note, Collection, Attachment


@pytest.fixture
def reader(test_db_path: Path) -> ZoteroReader:
    return ZoteroReader(test_db_path)


class TestGetItem:
    def test_get_existing_item(self, reader: ZoteroReader):
        item = reader.get_item("ATTN001")
        assert item is not None
        assert item.title == "Attention Is All You Need"
        assert item.item_type == "journalArticle"
        assert item.doi == "10.5555/attention"
        assert item.date == "2017"
        assert len(item.creators) == 2
        assert item.creators[0].last_name == "Vaswani"

    def test_get_nonexistent_item(self, reader: ZoteroReader):
        item = reader.get_item("NONEXIST")
        assert item is None

    def test_get_item_tags(self, reader: ZoteroReader):
        item = reader.get_item("ATTN001")
        assert "transformer" in item.tags
        assert "attention" in item.tags

    def test_get_item_collections(self, reader: ZoteroReader):
        item = reader.get_item("ATTN001")
        assert "COLML01" in item.collections

    def test_get_book(self, reader: ZoteroReader):
        item = reader.get_item("DEEP003")
        assert item.item_type == "book"
        assert item.title == "Deep Learning"


class TestSearch:
    def test_search_by_title(self, reader: ZoteroReader):
        result = reader.search("attention")
        assert result.total > 0
        assert any(i.key == "ATTN001" for i in result.items)

    def test_search_by_creator(self, reader: ZoteroReader):
        result = reader.search("Vaswani")
        assert result.total > 0
        assert any(i.key == "ATTN001" for i in result.items)

    def test_search_by_tag(self, reader: ZoteroReader):
        result = reader.search("transformer")
        assert result.total >= 2

    def test_search_no_results(self, reader: ZoteroReader):
        result = reader.search("nonexistentquery12345")
        assert result.total == 0

    def test_search_with_collection_filter(self, reader: ZoteroReader):
        result = reader.search("", collection="Transformers")
        assert result.total > 0
        assert all(i.key == "ATTN001" for i in result.items)

    def test_search_with_limit(self, reader: ZoteroReader):
        result = reader.search("", limit=1)
        assert len(result.items) == 1


class TestNotes:
    def test_get_notes(self, reader: ZoteroReader):
        notes = reader.get_notes("ATTN001")
        assert len(notes) == 1
        assert "transformer architecture" in notes[0].content

    def test_get_notes_empty(self, reader: ZoteroReader):
        notes = reader.get_notes("DEEP003")
        assert len(notes) == 0


class TestCollections:
    def test_get_collections(self, reader: ZoteroReader):
        collections = reader.get_collections()
        assert len(collections) >= 1
        ml = next(c for c in collections if c.name == "Machine Learning")
        assert any(ch.name == "Transformers" for ch in ml.children)

    def test_get_collection_items(self, reader: ZoteroReader):
        items = reader.get_collection_items("COLML01")
        assert len(items) >= 2


class TestAttachments:
    def test_get_attachments(self, reader: ZoteroReader):
        attachments = reader.get_attachments("ATTN001")
        assert len(attachments) == 1
        assert attachments[0].content_type == "application/pdf"
        assert attachments[0].filename == "attention.pdf"

    def test_get_pdf_attachment(self, reader: ZoteroReader):
        att = reader.get_pdf_attachment("ATTN001")
        assert att is not None
        assert att.key == "ATCH005"

    def test_get_pdf_attachment_none(self, reader: ZoteroReader):
        att = reader.get_pdf_attachment("DEEP003")
        assert att is None


class TestContextManager:
    def test_context_manager(self, test_db_path: Path):
        with ZoteroReader(test_db_path) as reader:
            item = reader.get_item("ATTN001")
            assert item is not None
        # Connection should be closed after exiting context
        assert reader._conn is None


class TestSchemaVersion:
    def test_check_schema_version(self, reader: ZoteroReader):
        version = reader.get_schema_version()
        assert version is not None
        assert isinstance(version, int)


class TestExportCitation:
    def test_export_bibtex(self, reader: ZoteroReader):
        bib = reader.export_citation("ATTN001", fmt="bibtex")
        assert "@article" in bib
        assert "Attention" in bib
        assert "Vaswani" in bib

    def test_export_nonexistent(self, reader: ZoteroReader):
        bib = reader.export_citation("NONEXIST", fmt="bibtex")
        assert bib is None


class TestRelatedItems:
    def test_explicit_relation(self, reader: ZoteroReader):
        related = reader.get_related_items("ATTN001")
        keys = [i.key for i in related]
        assert "BERT002" in keys

    def test_implicit_relation_shared_tags(self, reader: ZoteroReader):
        related = reader.get_related_items("ATTN001")
        keys = [i.key for i in related]
        assert "BERT002" in keys

    def test_no_relations(self, reader: ZoteroReader):
        related = reader.get_related_items("DEEP003")
        assert isinstance(related, list)
