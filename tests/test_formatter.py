import json

from zotero_cli_cc.formatter import format_collections, format_error, format_item_detail, format_items, format_notes
from zotero_cli_cc.models import Collection, Creator, Item, Note


def _make_item(key="K1", title="Test") -> Item:
    return Item(
        key=key,
        item_type="journalArticle",
        title=title,
        creators=[Creator("John", "Doe", "author")],
        abstract="Abstract.",
        date="2025",
        url=None,
        doi="10.1/x",
        tags=["ML"],
        collections=[],
        date_added="2025-01-01",
        date_modified="2025-01-02",
        extra={},
    )


def test_format_items_json():
    items = [_make_item()]
    result = format_items(items, output_json=True)
    data = json.loads(result)["data"]
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
    data = json.loads(result)["data"]
    assert data["title"] == "Test"


def test_format_item_detail_table():
    item = _make_item()
    result = format_item_detail(item, notes=[], output_json=False)
    assert "Test" in result
    assert "John Doe" in result


def test_format_collections_json():
    colls = [Collection(key="C1", name="ML", parent_key=None, children=[])]
    result = format_collections(colls, output_json=True)
    data = json.loads(result)["data"]
    assert data[0]["name"] == "ML"


def test_format_notes_json():
    notes = [Note(key="N1", parent_key="P1", content="Hello", tags=[])]
    result = format_notes(notes, output_json=True)
    data = json.loads(result)["data"]
    assert data[0]["content"] == "Hello"


def test_format_error_json_with_hint():
    from zotero_cli_cc.models import ErrorInfo

    err = ErrorInfo(message="Item 'XYZ' not found", context="read", hint="Run 'zot search' to find valid keys")
    result = format_error(err, output_json=True)
    env = json.loads(result)
    assert env["ok"] is False
    assert env["error"]["message"] == "Item 'XYZ' not found"
    assert env["error"]["context"] == "read"
    assert env["error"]["hint"] == "Run 'zot search' to find valid keys"
    assert env["error"]["code"] == "runtime_error"
    assert env["error"]["retryable"] is False


def test_format_error_text_with_hint():
    from zotero_cli_cc.models import ErrorInfo

    err = ErrorInfo(message="Item 'XYZ' not found", hint="Run 'zot search' to find valid keys")
    result = format_error(err, output_json=False)
    assert "Error: Item 'XYZ' not found" in result
    assert "Hint: Run 'zot search' to find valid keys" in result


def test_format_error_backward_compat_string():
    result = format_error("simple error", output_json=False)
    assert result == "Error: simple error"


def test_format_error_backward_compat_string_json():
    result = format_error("simple error", output_json=True)
    env = json.loads(result)
    assert env["ok"] is False
    assert env["error"]["message"] == "simple error"


def test_format_items_json_minimal():
    items = [_make_item()]
    result = format_items(items, output_json=True, detail="minimal")
    data = json.loads(result)["data"]
    assert data[0]["key"] == "K1"
    assert data[0]["title"] == "Test"
    assert "abstract" not in data[0]
    assert "extra" not in data[0]
    assert "collections" not in data[0]


def test_format_items_json_full():
    items = [_make_item()]
    result = format_items(items, output_json=True, detail="full")
    data = json.loads(result)["data"]
    assert "abstract" in data[0]
    assert "extra" in data[0]


def test_format_item_detail_minimal():
    item = _make_item()
    notes = [Note(key="N1", parent_key="K1", content="A note", tags=[])]
    result = format_item_detail(item, notes, output_json=False, detail="minimal")
    assert "Test" in result
    assert "Abstract" not in result
    assert "Notes" not in result


def test_format_item_detail_json_minimal():
    item = _make_item()
    notes = [Note(key="N1", parent_key="K1", content="A note", tags=[])]
    result = format_item_detail(item, notes, output_json=True, detail="minimal")
    data = json.loads(result)["data"]
    assert data["key"] == "K1"
    assert data["title"] == "Test"
    assert "abstract" not in data
    assert "notes" not in data


def test_format_item_detail_full():
    item = _make_item()
    notes = [Note(key="N1", parent_key="K1", content="A note", tags=[])]
    result = format_item_detail(item, notes, output_json=True, detail="full")
    data = json.loads(result)["data"]
    assert "abstract" in data
    assert "notes" in data
    assert "extra" in data
