import json

from zotero_cli_cc.formatter import format_items, format_item_detail, format_collections, format_notes
from zotero_cli_cc.models import Item, Creator, Collection, Note


def _make_item(key="K1", title="Test") -> Item:
    return Item(
        key=key, item_type="journalArticle", title=title,
        creators=[Creator("John", "Doe", "author")],
        abstract="Abstract.", date="2025", url=None, doi="10.1/x",
        tags=["ML"], collections=[], date_added="2025-01-01",
        date_modified="2025-01-02", extra={},
    )


def test_format_items_json():
    items = [_make_item()]
    result = format_items(items, output_json=True)
    data = json.loads(result)
    assert len(data) == 1
    assert data[0]["key"] == "K1"


def test_format_items_table():
    items = [_make_item()]
    result = format_items(items, output_json=False)
    assert "K1" in result
    assert "Test" in result


def test_format_item_detail_json():
    item = _make_item()
    result = format_item_detail(item, notes=[], output_json=True)
    data = json.loads(result)
    assert data["title"] == "Test"


def test_format_item_detail_table():
    item = _make_item()
    result = format_item_detail(item, notes=[], output_json=False)
    assert "Test" in result
    assert "John Doe" in result


def test_format_collections_json():
    colls = [Collection(key="C1", name="ML", parent_key=None, children=[])]
    result = format_collections(colls, output_json=True)
    data = json.loads(result)
    assert data[0]["name"] == "ML"


def test_format_notes_json():
    notes = [Note(key="N1", parent_key="P1", content="Hello", tags=[])]
    result = format_notes(notes, output_json=True)
    data = json.loads(result)
    assert data[0]["content"] == "Hello"
