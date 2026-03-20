# zotero-cli-cc Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python CLI tool (`zot`) that provides full Zotero interaction via SQLite reads and Web API writes, optimized for Claude Code workflows.

**Architecture:** Hybrid data strategy — `ZoteroReader` reads directly from Zotero's SQLite database (EAV model, read-only, offline-capable), `ZoteroWriter` uses `pyzotero` for Web API writes. CLI built with Click, output with Rich.

**Tech Stack:** Python >= 3.10, Click, pyzotero, pymupdf, Rich, platformdirs, uv

**Spec:** `docs/superpowers/specs/2026-03-20-zotero-cli-cc-design.md`

---

## File Map

| File | Responsibility |
|------|---------------|
| `pyproject.toml` | Package config, dependencies, `[project.scripts]` entry point |
| `src/zotero_cli_cc/__init__.py` | Package version |
| `src/zotero_cli_cc/models.py` | Dataclasses: Item, Creator, Note, Collection, Attachment, SearchResult |
| `src/zotero_cli_cc/config.py` | Config load/save/init, path detection |
| `src/zotero_cli_cc/core/reader.py` | ZoteroReader: all SQLite queries |
| `src/zotero_cli_cc/core/writer.py` | ZoteroWriter: all pyzotero Web API calls |
| `src/zotero_cli_cc/core/pdf_extractor.py` | PDF text extraction via pymupdf |
| `src/zotero_cli_cc/formatter.py` | Output formatting: table (Rich) and JSON |
| `src/zotero_cli_cc/cli.py` | Click group, global flags, command registration |
| `src/zotero_cli_cc/commands/config.py` | `zot config init/set/show` |
| `src/zotero_cli_cc/commands/search.py` | `zot search` |
| `src/zotero_cli_cc/commands/list_cmd.py` | `zot list` (avoid shadowing `list` builtin) |
| `src/zotero_cli_cc/commands/read.py` | `zot read` |
| `src/zotero_cli_cc/commands/note.py` | `zot note` |
| `src/zotero_cli_cc/commands/export.py` | `zot export` |
| `src/zotero_cli_cc/commands/add.py` | `zot add` |
| `src/zotero_cli_cc/commands/delete.py` | `zot delete` |
| `src/zotero_cli_cc/commands/tag.py` | `zot tag` |
| `src/zotero_cli_cc/commands/collection.py` | `zot collection` |
| `src/zotero_cli_cc/commands/summarize.py` | `zot summarize` |
| `src/zotero_cli_cc/commands/pdf.py` | `zot pdf` |
| `src/zotero_cli_cc/commands/relate.py` | `zot relate` |
| `tests/conftest.py` | Shared fixtures: test DB, config, CliRunner |
| `tests/fixtures/create_test_db.py` | Script to generate fixture `zotero.sqlite` |
| `tests/fixtures/zotero.sqlite` | Generated test database |
| `tests/fixtures/test.pdf` | Small PDF for extraction tests |
| `tests/test_models.py` | Model unit tests |
| `tests/test_config.py` | Config load/save tests |
| `tests/test_reader.py` | ZoteroReader tests against fixture DB |
| `tests/test_writer.py` | ZoteroWriter tests with mocked pyzotero |
| `tests/test_pdf_extractor.py` | PDF extraction tests |
| `tests/test_formatter.py` | Output formatting tests |
| `tests/test_cli_*.py` | CLI integration tests per command group |

---

## Task 1: Project Scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `src/zotero_cli_cc/__init__.py`

- [ ] **Step 1: Initialize uv project**

```bash
cd /Users/niehu/github/zotero-cli-cc
uv init --lib --name zotero-cli-cc
```

- [ ] **Step 2: Configure pyproject.toml**

```toml
[project]
name = "zotero-cli-cc"
version = "0.1.0"
description = "Zotero CLI for Claude Code — SQLite reads + Web API writes"
requires-python = ">=3.10"
dependencies = [
    "click>=8.1",
    "pyzotero>=1.5",
    "pymupdf>=1.24",
    "rich>=13.0",
    "platformdirs>=4.0",
    "tomli>=2.0; python_version < '3.11'",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-cov>=5.0",
]

[project.scripts]
zot = "zotero_cli_cc.cli:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.backends"

[tool.hatch.build.targets.wheel]
packages = ["src/zotero_cli_cc"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 3: Create __init__.py**

```python
"""zotero-cli-cc: Zotero CLI for Claude Code."""

__version__ = "0.1.0"
```

- [ ] **Step 4: Install in dev mode**

```bash
uv add --dev pytest pytest-cov
uv sync
```

Run: `uv run python -c "import zotero_cli_cc; print(zotero_cli_cc.__version__)"`
Expected: `0.1.0`

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml src/ uv.lock
git commit -m "chore: scaffold project with uv, dependencies, and entry point"
```

---

## Task 2: Data Models

**Files:**
- Create: `src/zotero_cli_cc/models.py`
- Create: `tests/test_models.py`

- [ ] **Step 1: Write tests for data models**

```python
# tests/test_models.py
from zotero_cli_cc.models import Item, Creator, Note, Collection, Attachment, SearchResult


def test_creator_full_name():
    c = Creator(first_name="John", last_name="Doe", creator_type="author")
    assert c.full_name == "John Doe"


def test_creator_full_name_last_only():
    c = Creator(first_name="", last_name="Doe", creator_type="author")
    assert c.full_name == "Doe"


def test_item_creation():
    item = Item(
        key="ABC123",
        item_type="journalArticle",
        title="Test Paper",
        creators=[Creator("Jane", "Doe", "author")],
        abstract="An abstract.",
        date="2025",
        url=None,
        doi="10.1234/test",
        tags=["ML", "NLP"],
        collections=["COL1"],
        date_added="2025-01-01",
        date_modified="2025-01-02",
        extra={},
    )
    assert item.key == "ABC123"
    assert item.creators[0].full_name == "Jane Doe"


def test_collection_tree():
    child = Collection(key="C2", name="Sub", parent_key="C1", children=[])
    parent = Collection(key="C1", name="Root", parent_key=None, children=[child])
    assert parent.children[0].name == "Sub"


def test_search_result():
    sr = SearchResult(items=[], total=0, query="test")
    assert sr.total == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_models.py -v`
Expected: FAIL (ImportError)

- [ ] **Step 3: Implement models**

```python
# src/zotero_cli_cc/models.py
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Creator:
    first_name: str
    last_name: str
    creator_type: str

    @property
    def full_name(self) -> str:
        parts = [p for p in (self.first_name, self.last_name) if p]
        return " ".join(parts)


@dataclass
class Item:
    key: str
    item_type: str
    title: str
    creators: list[Creator]
    abstract: str | None
    date: str | None
    url: str | None
    doi: str | None
    tags: list[str]
    collections: list[str]
    date_added: str
    date_modified: str
    extra: dict[str, str] = field(default_factory=dict)


@dataclass
class Note:
    key: str
    parent_key: str
    content: str
    tags: list[str] = field(default_factory=list)


@dataclass
class Collection:
    key: str
    name: str
    parent_key: str | None
    children: list[Collection] = field(default_factory=list)


@dataclass
class Attachment:
    key: str
    parent_key: str
    filename: str
    content_type: str
    path: Path | None = None


@dataclass
class SearchResult:
    items: list[Item]
    total: int
    query: str
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_models.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/zotero_cli_cc/models.py tests/test_models.py
git commit -m "feat: add data models (Item, Creator, Note, Collection, Attachment, SearchResult)"
```

---

## Task 3: Configuration System

**Files:**
- Create: `src/zotero_cli_cc/config.py`
- Create: `tests/test_config.py`

- [ ] **Step 1: Write tests for config**

```python
# tests/test_config.py
import sys
from pathlib import Path

from zotero_cli_cc.config import AppConfig, load_config, save_config, detect_zotero_data_dir


def test_default_config():
    cfg = AppConfig()
    assert cfg.library_id == ""
    assert cfg.api_key == ""
    assert cfg.default_format == "table"
    assert cfg.default_limit == 50
    assert cfg.default_export_style == "bibtex"


def test_save_and_load_config(tmp_path):
    config_path = tmp_path / "config.toml"
    cfg = AppConfig(library_id="123", api_key="abc")
    save_config(cfg, config_path)
    loaded = load_config(config_path)
    assert loaded.library_id == "123"
    assert loaded.api_key == "abc"


def test_load_missing_config(tmp_path):
    config_path = tmp_path / "nonexistent.toml"
    cfg = load_config(config_path)
    assert cfg.library_id == ""


def test_detect_zotero_data_dir_with_override(tmp_path):
    db = tmp_path / "zotero.sqlite"
    db.touch()
    cfg = AppConfig(data_dir=str(tmp_path))
    result = detect_zotero_data_dir(cfg)
    assert result == tmp_path


def test_detect_zotero_data_dir_default(monkeypatch):
    result = detect_zotero_data_dir(AppConfig())
    # Should return ~/Zotero on macOS/Linux or %APPDATA%/Zotero on Windows
    if sys.platform == "win32":
        assert "Zotero" in str(result)
    else:
        assert result == Path.home() / "Zotero"


def test_config_has_write_credentials():
    cfg = AppConfig(library_id="123", api_key="abc")
    assert cfg.has_write_credentials is True
    cfg2 = AppConfig()
    assert cfg2.has_write_credentials is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_config.py -v`
Expected: FAIL (ImportError)

- [ ] **Step 3: Implement config**

```python
# src/zotero_cli_cc/config.py
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

from platformdirs import user_config_dir

if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomllib
    except ModuleNotFoundError:
        import tomli as tomllib  # type: ignore[no-redef]

CONFIG_DIR = Path(user_config_dir("zot"))
CONFIG_FILE = CONFIG_DIR / "config.toml"


@dataclass
class AppConfig:
    data_dir: str = ""
    library_id: str = ""
    api_key: str = ""
    default_format: str = "table"
    default_limit: int = 50
    default_export_style: str = "bibtex"

    @property
    def has_write_credentials(self) -> bool:
        return bool(self.library_id and self.api_key)


def load_config(path: Path | None = None) -> AppConfig:
    path = path or CONFIG_FILE
    if not path.exists():
        return AppConfig()
    with open(path, "rb") as f:
        data = tomllib.load(f)
    zotero = data.get("zotero", {})
    output = data.get("output", {})
    export = data.get("export", {})
    return AppConfig(
        data_dir=zotero.get("data_dir", ""),
        library_id=zotero.get("library_id", ""),
        api_key=zotero.get("api_key", ""),
        default_format=output.get("default_format", "table"),
        default_limit=output.get("limit", 50),
        default_export_style=export.get("default_style", "bibtex"),
    )


def save_config(config: AppConfig, path: Path | None = None) -> None:
    path = path or CONFIG_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "[zotero]",
        f'data_dir = "{config.data_dir}"',
        f'library_id = "{config.library_id}"',
        f'api_key = "{config.api_key}"',
        "",
        "[output]",
        f'default_format = "{config.default_format}"',
        f"limit = {config.default_limit}",
        "",
        "[export]",
        f'default_style = "{config.default_export_style}"',
        "",
    ]
    path.write_text("\n".join(lines))


def detect_zotero_data_dir(config: AppConfig) -> Path:
    if config.data_dir:
        return Path(config.data_dir).expanduser()
    if sys.platform == "win32":
        import os
        return Path(os.environ.get("APPDATA", "")) / "Zotero"
    return Path.home() / "Zotero"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_config.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/zotero_cli_cc/config.py tests/test_config.py
git commit -m "feat: add configuration system with TOML load/save and path detection"
```

---

## Task 4: Test Database Fixture

**Files:**
- Create: `tests/fixtures/create_test_db.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Create test DB generator**

This script creates a minimal Zotero-compatible SQLite database with known test data.

```python
# tests/fixtures/create_test_db.py
"""Generate a minimal Zotero-compatible SQLite test fixture."""
import sqlite3
from pathlib import Path

FIXTURE_DIR = Path(__file__).parent
DB_PATH = FIXTURE_DIR / "zotero.sqlite"


def create_test_db() -> None:
    if DB_PATH.exists():
        DB_PATH.unlink()

    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()

    # Core schema (simplified from Zotero source)
    c.executescript("""
        CREATE TABLE libraries (libraryID INTEGER PRIMARY KEY, type TEXT NOT NULL, editable INT NOT NULL DEFAULT 1, filesEditable INT NOT NULL DEFAULT 1);
        INSERT INTO libraries VALUES (1, 'user', 1, 1);

        CREATE TABLE itemTypes (itemTypeID INTEGER PRIMARY KEY, typeName TEXT NOT NULL);
        INSERT INTO itemTypes VALUES (2, 'journalArticle');
        INSERT INTO itemTypes VALUES (3, 'book');
        INSERT INTO itemTypes VALUES (26, 'note');
        INSERT INTO itemTypes VALUES (14, 'attachment');

        CREATE TABLE fields (fieldID INTEGER PRIMARY KEY, fieldName TEXT NOT NULL);
        INSERT INTO fields VALUES (1, 'url');
        INSERT INTO fields VALUES (4, 'title');
        INSERT INTO fields VALUES (6, 'abstractNote');
        INSERT INTO fields VALUES (14, 'date');
        INSERT INTO fields VALUES (26, 'DOI');

        CREATE TABLE items (
            itemID INTEGER PRIMARY KEY,
            itemTypeID INT NOT NULL REFERENCES itemTypes(itemTypeID),
            dateAdded TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            dateModified TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            clientDateModified TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            libraryID INT NOT NULL REFERENCES libraries(libraryID),
            key TEXT NOT NULL UNIQUE
        );

        CREATE TABLE itemData (itemID INT NOT NULL, fieldID INT NOT NULL, valueID INT NOT NULL, PRIMARY KEY (itemID, fieldID));
        CREATE TABLE itemDataValues (valueID INTEGER PRIMARY KEY, value TEXT NOT NULL);

        CREATE TABLE creatorTypes (creatorTypeID INTEGER PRIMARY KEY, creatorType TEXT NOT NULL);
        INSERT INTO creatorTypes VALUES (1, 'author');
        INSERT INTO creatorTypes VALUES (2, 'editor');

        CREATE TABLE creators (creatorID INTEGER PRIMARY KEY, firstName TEXT, lastName TEXT NOT NULL);
        CREATE TABLE itemCreators (itemID INT NOT NULL, creatorID INT NOT NULL, creatorTypeID INT NOT NULL DEFAULT 1, orderIndex INT NOT NULL DEFAULT 0, PRIMARY KEY (itemID, creatorID, creatorTypeID, orderIndex));

        CREATE TABLE tags (tagID INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE);
        CREATE TABLE itemTags (itemID INT NOT NULL, tagID INT NOT NULL, type INT NOT NULL DEFAULT 0, PRIMARY KEY (itemID, tagID));

        CREATE TABLE collections (collectionID INTEGER PRIMARY KEY, collectionName TEXT NOT NULL, parentCollectionID INT, libraryID INT NOT NULL, key TEXT NOT NULL UNIQUE);
        CREATE TABLE collectionItems (collectionID INT NOT NULL, itemID INT NOT NULL, orderIndex INT NOT NULL DEFAULT 0, PRIMARY KEY (collectionID, itemID));

        CREATE TABLE itemNotes (itemID INT PRIMARY KEY, parentItemID INT, note TEXT, title TEXT);

        CREATE TABLE itemAttachments (
            itemID INT PRIMARY KEY,
            parentItemID INT,
            linkMode INT,
            contentType TEXT,
            charsetID INT,
            path TEXT
        );

        CREATE TABLE itemRelations (itemID INT NOT NULL, predicateID INT NOT NULL, object TEXT NOT NULL, PRIMARY KEY (itemID, predicateID, object));
        CREATE TABLE relationPredicates (predicateID INTEGER PRIMARY KEY, predicate TEXT NOT NULL UNIQUE);
        INSERT INTO relationPredicates VALUES (1, 'dc:relation');

        CREATE TABLE fulltextItemWords (wordID INT NOT NULL, itemID INT NOT NULL, PRIMARY KEY (wordID, itemID));
        CREATE TABLE fulltextWords (wordID INTEGER PRIMARY KEY, word TEXT NOT NULL UNIQUE);

        CREATE TABLE version (schema TEXT PRIMARY KEY, version INT NOT NULL);
        INSERT INTO version VALUES ('userdata', 120);
    """)

    # Test data: 2 journal articles, 1 book
    # Item 1: "Attention Is All You Need"
    c.execute("INSERT INTO items VALUES (1, 2, '2024-01-01', '2024-01-02', '2024-01-02', 1, 'ATTN001')")
    c.execute("INSERT INTO itemDataValues VALUES (1, 'Attention Is All You Need')")
    c.execute("INSERT INTO itemDataValues VALUES (2, 'We propose a new architecture...')")
    c.execute("INSERT INTO itemDataValues VALUES (3, '2017')")
    c.execute("INSERT INTO itemDataValues VALUES (4, '10.5555/attention')")
    c.execute("INSERT INTO itemData VALUES (1, 4, 1)")   # title
    c.execute("INSERT INTO itemData VALUES (1, 6, 2)")   # abstract
    c.execute("INSERT INTO itemData VALUES (1, 14, 3)")  # date
    c.execute("INSERT INTO itemData VALUES (1, 26, 4)")  # DOI
    c.execute("INSERT INTO creators VALUES (1, 'Ashish', 'Vaswani')")
    c.execute("INSERT INTO creators VALUES (2, 'Noam', 'Shazeer')")
    c.execute("INSERT INTO itemCreators VALUES (1, 1, 1, 0)")
    c.execute("INSERT INTO itemCreators VALUES (1, 2, 1, 1)")
    c.execute("INSERT INTO tags VALUES (1, 'transformer')")
    c.execute("INSERT INTO tags VALUES (2, 'attention')")
    c.execute("INSERT INTO tags VALUES (3, 'NLP')")
    c.execute("INSERT INTO itemTags VALUES (1, 1, 0)")
    c.execute("INSERT INTO itemTags VALUES (1, 2, 0)")

    # Item 2: "BERT: Pre-training of Deep Bidirectional Transformers"
    c.execute("INSERT INTO items VALUES (2, 2, '2024-02-01', '2024-02-02', '2024-02-02', 1, 'BERT002')")
    c.execute("INSERT INTO itemDataValues VALUES (5, 'BERT: Pre-training of Deep Bidirectional Transformers')")
    c.execute("INSERT INTO itemDataValues VALUES (6, 'We introduce BERT...')")
    c.execute("INSERT INTO itemDataValues VALUES (7, '2019')")
    c.execute("INSERT INTO itemDataValues VALUES (8, '10.5555/bert')")
    c.execute("INSERT INTO itemData VALUES (2, 4, 5)")
    c.execute("INSERT INTO itemData VALUES (2, 6, 6)")
    c.execute("INSERT INTO itemData VALUES (2, 14, 7)")
    c.execute("INSERT INTO itemData VALUES (2, 26, 8)")
    c.execute("INSERT INTO creators VALUES (3, 'Jacob', 'Devlin')")
    c.execute("INSERT INTO itemCreators VALUES (2, 3, 1, 0)")
    c.execute("INSERT INTO itemTags VALUES (2, 1, 0)")  # transformer
    c.execute("INSERT INTO itemTags VALUES (2, 3, 0)")  # NLP

    # Item 3: Book "Deep Learning"
    c.execute("INSERT INTO items VALUES (3, 3, '2024-03-01', '2024-03-02', '2024-03-02', 1, 'DEEP003')")
    c.execute("INSERT INTO itemDataValues VALUES (9, 'Deep Learning')")
    c.execute("INSERT INTO itemDataValues VALUES (10, 'An MIT Press book...')")
    c.execute("INSERT INTO itemDataValues VALUES (11, '2016')")
    c.execute("INSERT INTO itemData VALUES (3, 4, 9)")
    c.execute("INSERT INTO itemData VALUES (3, 6, 10)")
    c.execute("INSERT INTO itemData VALUES (3, 14, 11)")
    c.execute("INSERT INTO creators VALUES (4, 'Ian', 'Goodfellow')")
    c.execute("INSERT INTO itemCreators VALUES (3, 4, 1, 0)")

    # Collections
    c.execute("INSERT INTO collections VALUES (1, 'Machine Learning', NULL, 1, 'COLML01')")
    c.execute("INSERT INTO collections VALUES (2, 'Transformers', 1, 1, 'COLTR02')")
    c.execute("INSERT INTO collectionItems VALUES (1, 1, 0)")
    c.execute("INSERT INTO collectionItems VALUES (1, 2, 0)")
    c.execute("INSERT INTO collectionItems VALUES (2, 1, 0)")
    c.execute("INSERT INTO collectionItems VALUES (1, 3, 0)")

    # Notes
    c.execute("INSERT INTO items VALUES (4, 26, '2024-01-03', '2024-01-03', '2024-01-03', 1, 'NOTE004')")
    c.execute("INSERT INTO itemNotes VALUES (4, 1, '<p>This paper introduces the transformer architecture.</p>', 'Transformer note')")

    # Attachment (PDF) for item 1
    c.execute("INSERT INTO items VALUES (5, 14, '2024-01-01', '2024-01-01', '2024-01-01', 1, 'ATCH005')")
    c.execute("INSERT INTO itemAttachments VALUES (5, 1, 0, 'application/pdf', NULL, 'storage:attention.pdf')")

    # Relations: item 1 and item 2 are related
    c.execute("INSERT INTO itemRelations VALUES (1, 1, 'http://zotero.org/users/local/BERT002')")

    # Fulltext index for item 1
    c.execute("INSERT INTO fulltextWords VALUES (1, 'transformer')")
    c.execute("INSERT INTO fulltextWords VALUES (2, 'attention')")
    c.execute("INSERT INTO fulltextWords VALUES (3, 'mechanism')")
    c.execute("INSERT INTO fulltextItemWords VALUES (1, 5)")  # attachment itemID
    c.execute("INSERT INTO fulltextItemWords VALUES (2, 5)")
    c.execute("INSERT INTO fulltextItemWords VALUES (3, 5)")

    conn.commit()
    conn.close()
    print(f"Created test DB at {DB_PATH}")


if __name__ == "__main__":
    create_test_db()
```

- [ ] **Step 2: Generate the fixture DB**

Run: `uv run python tests/fixtures/create_test_db.py`
Expected: `Created test DB at tests/fixtures/zotero.sqlite`

- [ ] **Step 3: Create conftest.py with shared fixtures**

```python
# tests/conftest.py
from pathlib import Path

import pytest

from zotero_cli_cc.config import AppConfig

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def test_db_path() -> Path:
    return FIXTURES_DIR / "zotero.sqlite"


@pytest.fixture
def test_config(test_db_path: Path) -> AppConfig:
    return AppConfig(data_dir=str(test_db_path.parent))


@pytest.fixture
def test_data_dir() -> Path:
    return FIXTURES_DIR
```

- [ ] **Step 4: Verify fixture loads**

Run: `uv run python -c "import sqlite3; conn = sqlite3.connect('tests/fixtures/zotero.sqlite'); print(conn.execute('SELECT key FROM items').fetchall())"`
Expected: `[('ATTN001',), ('BERT002',), ('DEEP003',), ('NOTE004',), ('ATCH005',)]`

- [ ] **Step 5: Commit**

```bash
git add tests/fixtures/create_test_db.py tests/fixtures/zotero.sqlite tests/conftest.py
git commit -m "test: add Zotero SQLite fixture DB and shared test fixtures"
```

---

## Task 5: ZoteroReader — Core SQLite Queries

**Files:**
- Create: `src/zotero_cli_cc/core/__init__.py`
- Create: `src/zotero_cli_cc/core/reader.py`
- Create: `tests/test_reader.py`

- [ ] **Step 1: Write tests for ZoteroReader**

```python
# tests/test_reader.py
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
        result = reader.search("NLP")
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
        # BERT002 shares 'transformer' and 'NLP' tags (2+ overlap)
        keys = [i.key for i in related]
        assert "BERT002" in keys

    def test_no_relations(self, reader: ZoteroReader):
        related = reader.get_related_items("DEEP003")
        # DEEP003 has no explicit relations and only 0-1 shared tags
        assert isinstance(related, list)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_reader.py -v`
Expected: FAIL (ImportError)

- [ ] **Step 3: Create core/__init__.py**

```python
# src/zotero_cli_cc/core/__init__.py
```

- [ ] **Step 4: Implement ZoteroReader**

```python
# src/zotero_cli_cc/core/reader.py
from __future__ import annotations

import re
import shutil
import sqlite3
import tempfile
import time
from pathlib import Path

from zotero_cli_cc.models import (
    Attachment,
    Collection,
    Creator,
    Item,
    Note,
    SearchResult,
)

MAX_RETRIES = 3
RETRY_DELAY = 1.0


class ZoteroReader:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._conn: sqlite3.Connection | None = None

    def _connect(self) -> sqlite3.Connection:
        if self._conn is not None:
            return self._conn
        for attempt in range(MAX_RETRIES):
            try:
                conn = sqlite3.connect(
                    f"file:{self._db_path}?mode=ro", uri=True
                )
                conn.row_factory = sqlite3.Row
                self._conn = conn
                return conn
            except sqlite3.OperationalError:
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY)
                    continue
                # Fallback: copy DB to temp file
                tmp = Path(tempfile.mkdtemp()) / "zotero.sqlite"
                shutil.copy2(self._db_path, tmp)
                wal = self._db_path.with_suffix(".sqlite-wal")
                shm = self._db_path.with_suffix(".sqlite-shm")
                if wal.exists():
                    shutil.copy2(wal, tmp.with_suffix(".sqlite-wal"))
                if shm.exists():
                    shutil.copy2(shm, tmp.with_suffix(".sqlite-shm"))
                conn = sqlite3.connect(f"file:{tmp}?mode=ro", uri=True)
                conn.row_factory = sqlite3.Row
                self._conn = conn
                return conn

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    def get_item(self, key: str) -> Item | None:
        conn = self._connect()
        row = conn.execute(
            "SELECT itemID, itemTypeID, key, dateAdded, dateModified "
            "FROM items WHERE key = ? AND itemTypeID NOT IN (26, 14)",
            (key,),
        ).fetchone()
        if row is None:
            return None
        item_id = row["itemID"]
        item_type = conn.execute(
            "SELECT typeName FROM itemTypes WHERE itemTypeID = ?",
            (row["itemTypeID"],),
        ).fetchone()["typeName"]
        fields = self._get_item_fields(conn, item_id)
        creators = self._get_item_creators(conn, item_id)
        tags = self._get_item_tags(conn, item_id)
        collections = self._get_item_collections(conn, item_id)
        return Item(
            key=key,
            item_type=item_type,
            title=fields.get("title", ""),
            creators=creators,
            abstract=fields.get("abstractNote"),
            date=fields.get("date"),
            url=fields.get("url"),
            doi=fields.get("DOI"),
            tags=tags,
            collections=collections,
            date_added=row["dateAdded"],
            date_modified=row["dateModified"],
            extra={k: v for k, v in fields.items()
                   if k not in ("title", "abstractNote", "date", "url", "DOI")},
        )

    def search(
        self,
        query: str,
        collection: str | None = None,
        limit: int = 50,
    ) -> SearchResult:
        conn = self._connect()
        item_ids: set[int] = set()
        params: list[str] = []

        if query:
            like = f"%{query}%"
            # Search titles and abstracts
            rows = conn.execute(
                "SELECT DISTINCT i.itemID FROM items i "
                "JOIN itemData id ON i.itemID = id.itemID "
                "JOIN itemDataValues iv ON id.valueID = iv.valueID "
                "WHERE iv.value LIKE ? AND i.itemTypeID NOT IN (26, 14)",
                (like,),
            ).fetchall()
            item_ids.update(r["itemID"] for r in rows)

            # Search creators
            rows = conn.execute(
                "SELECT DISTINCT ic.itemID FROM itemCreators ic "
                "JOIN creators c ON ic.creatorID = c.creatorID "
                "WHERE c.firstName LIKE ? OR c.lastName LIKE ?",
                (like, like),
            ).fetchall()
            item_ids.update(r["itemID"] for r in rows)

            # Search tags
            rows = conn.execute(
                "SELECT DISTINCT it.itemID FROM itemTags it "
                "JOIN tags t ON it.tagID = t.tagID "
                "WHERE t.name LIKE ?",
                (like,),
            ).fetchall()
            item_ids.update(r["itemID"] for r in rows)

            # Search fulltext
            rows = conn.execute(
                "SELECT DISTINCT ia.parentItemID FROM fulltextItemWords fw "
                "JOIN fulltextWords w ON fw.wordID = w.wordID "
                "JOIN itemAttachments ia ON fw.itemID = ia.itemID "
                "WHERE w.word LIKE ? AND ia.parentItemID IS NOT NULL",
                (like,),
            ).fetchall()
            item_ids.update(r["parentItemID"] for r in rows)
        else:
            # No query: return all items
            rows = conn.execute(
                "SELECT itemID FROM items WHERE itemTypeID NOT IN (26, 14)"
            ).fetchall()
            item_ids.update(r["itemID"] for r in rows)

        # Filter by collection
        if collection:
            col_row = conn.execute(
                "SELECT collectionID FROM collections WHERE collectionName = ?",
                (collection,),
            ).fetchone()
            if col_row:
                col_items = conn.execute(
                    "SELECT itemID FROM collectionItems WHERE collectionID = ?",
                    (col_row["collectionID"],),
                ).fetchall()
                col_item_ids = {r["itemID"] for r in col_items}
                item_ids &= col_item_ids
            else:
                item_ids = set()

        # Resolve items
        items: list[Item] = []
        for item_id in sorted(item_ids):
            key_row = conn.execute(
                "SELECT key FROM items WHERE itemID = ?", (item_id,)
            ).fetchone()
            if key_row:
                item = self.get_item(key_row["key"])
                if item:
                    items.append(item)
            if len(items) >= limit:
                break

        return SearchResult(items=items, total=len(item_ids), query=query)

    def get_notes(self, key: str) -> list[Note]:
        conn = self._connect()
        parent = conn.execute(
            "SELECT itemID FROM items WHERE key = ?", (key,)
        ).fetchone()
        if parent is None:
            return []
        rows = conn.execute(
            "SELECT i.key, n.note FROM itemNotes n "
            "JOIN items i ON n.itemID = i.itemID "
            "WHERE n.parentItemID = ?",
            (parent["itemID"],),
        ).fetchall()
        notes = []
        for r in rows:
            content = self._html_to_markdown(r["note"] or "")
            tags = self._get_item_tags(
                conn,
                conn.execute(
                    "SELECT itemID FROM items WHERE key = ?", (r["key"],)
                ).fetchone()["itemID"],
            )
            notes.append(Note(key=r["key"], parent_key=key, content=content, tags=tags))
        return notes

    def get_collections(self) -> list[Collection]:
        conn = self._connect()
        rows = conn.execute(
            "SELECT collectionID, collectionName, parentCollectionID, key "
            "FROM collections"
        ).fetchall()
        coll_map: dict[int, Collection] = {}
        parent_map: dict[int, int | None] = {}
        for r in rows:
            coll_map[r["collectionID"]] = Collection(
                key=r["key"],
                name=r["collectionName"],
                parent_key=None,
                children=[],
            )
            parent_map[r["collectionID"]] = r["parentCollectionID"]

        # Build tree
        for cid, parent_cid in parent_map.items():
            if parent_cid and parent_cid in coll_map:
                coll_map[cid].parent_key = coll_map[parent_cid].key
                coll_map[parent_cid].children.append(coll_map[cid])

        return [c for cid, c in coll_map.items() if parent_map[cid] is None]

    def get_collection_items(self, collection_key: str) -> list[Item]:
        conn = self._connect()
        col_row = conn.execute(
            "SELECT collectionID FROM collections WHERE key = ?",
            (collection_key,),
        ).fetchone()
        if col_row is None:
            return []
        rows = conn.execute(
            "SELECT i.key FROM collectionItems ci "
            "JOIN items i ON ci.itemID = i.itemID "
            "WHERE ci.collectionID = ? AND i.itemTypeID NOT IN (26, 14)",
            (col_row["collectionID"],),
        ).fetchall()
        items = []
        for r in rows:
            item = self.get_item(r["key"])
            if item:
                items.append(item)
        return items

    def get_attachments(self, key: str) -> list[Attachment]:
        conn = self._connect()
        parent = conn.execute(
            "SELECT itemID FROM items WHERE key = ?", (key,)
        ).fetchone()
        if parent is None:
            return []
        rows = conn.execute(
            "SELECT i.key, ia.contentType, ia.path "
            "FROM itemAttachments ia "
            "JOIN items i ON ia.itemID = i.itemID "
            "WHERE ia.parentItemID = ?",
            (parent["itemID"],),
        ).fetchall()
        attachments = []
        for r in rows:
            raw_path = r["path"] or ""
            filename = raw_path.replace("storage:", "") if raw_path.startswith("storage:") else raw_path
            attachments.append(Attachment(
                key=r["key"],
                parent_key=key,
                filename=filename,
                content_type=r["contentType"] or "",
                path=None,
            ))
        return attachments

    def get_pdf_attachment(self, key: str) -> Attachment | None:
        for att in self.get_attachments(key):
            if att.content_type == "application/pdf":
                return att
        return None

    # --- Private helpers ---

    def _get_item_fields(self, conn: sqlite3.Connection, item_id: int) -> dict[str, str]:
        rows = conn.execute(
            "SELECT f.fieldName, iv.value FROM itemData id "
            "JOIN fields f ON id.fieldID = f.fieldID "
            "JOIN itemDataValues iv ON id.valueID = iv.valueID "
            "WHERE id.itemID = ?",
            (item_id,),
        ).fetchall()
        return {r["fieldName"]: r["value"] for r in rows}

    def _get_item_creators(self, conn: sqlite3.Connection, item_id: int) -> list[Creator]:
        rows = conn.execute(
            "SELECT c.firstName, c.lastName, ct.creatorType "
            "FROM itemCreators ic "
            "JOIN creators c ON ic.creatorID = c.creatorID "
            "JOIN creatorTypes ct ON ic.creatorTypeID = ct.creatorTypeID "
            "WHERE ic.itemID = ? ORDER BY ic.orderIndex",
            (item_id,),
        ).fetchall()
        return [Creator(r["firstName"] or "", r["lastName"], r["creatorType"]) for r in rows]

    def _get_item_tags(self, conn: sqlite3.Connection, item_id: int) -> list[str]:
        rows = conn.execute(
            "SELECT t.name FROM itemTags it "
            "JOIN tags t ON it.tagID = t.tagID "
            "WHERE it.itemID = ?",
            (item_id,),
        ).fetchall()
        return [r["name"] for r in rows]

    def _get_item_collections(self, conn: sqlite3.Connection, item_id: int) -> list[str]:
        rows = conn.execute(
            "SELECT c.key FROM collectionItems ci "
            "JOIN collections c ON ci.collectionID = c.collectionID "
            "WHERE ci.itemID = ?",
            (item_id,),
        ).fetchall()
        return [r["key"] for r in rows]

    def get_schema_version(self) -> int | None:
        conn = self._connect()
        row = conn.execute(
            "SELECT version FROM version WHERE schema = 'userdata'"
        ).fetchone()
        return row["version"] if row else None

    def check_schema_compatibility(self) -> None:
        """Warn if schema version is outside known-good range."""
        import warnings
        version = self.get_schema_version()
        if version and (version < 100 or version > 200):
            warnings.warn(
                f"Zotero schema version {version} is outside the tested range (100-200). "
                "Some queries may not work correctly.",
                stacklevel=2,
            )

    def export_citation(self, key: str, fmt: str = "bibtex") -> str | None:
        item = self.get_item(key)
        if item is None:
            return None
        if fmt == "bibtex":
            return self._to_bibtex(item)
        return None

    def get_related_items(self, key: str, limit: int = 20) -> list[Item]:
        conn = self._connect()
        parent = conn.execute(
            "SELECT itemID FROM items WHERE key = ?", (key,)
        ).fetchone()
        if parent is None:
            return []
        item_id = parent["itemID"]
        related_ids: dict[int, int] = {}  # itemID -> score

        # Explicit relations
        rows = conn.execute(
            "SELECT object FROM itemRelations WHERE itemID = ? AND predicateID = 1",
            (item_id,),
        ).fetchall()
        for r in rows:
            obj = r["object"]
            rel_key = obj.rsplit("/", 1)[-1] if "/" in obj else obj
            rel_row = conn.execute(
                "SELECT itemID FROM items WHERE key = ?", (rel_key,)
            ).fetchone()
            if rel_row:
                related_ids[rel_row["itemID"]] = related_ids.get(rel_row["itemID"], 0) + 100

        # Implicit: shared collections
        my_cols = {r["collectionID"] for r in conn.execute(
            "SELECT collectionID FROM collectionItems WHERE itemID = ?", (item_id,)
        ).fetchall()}
        if my_cols:
            placeholders = ",".join("?" * len(my_cols))
            rows = conn.execute(
                f"SELECT itemID, COUNT(*) as cnt FROM collectionItems "
                f"WHERE collectionID IN ({placeholders}) AND itemID != ? "
                f"GROUP BY itemID",
                (*my_cols, item_id),
            ).fetchall()
            for r in rows:
                related_ids[r["itemID"]] = related_ids.get(r["itemID"], 0) + r["cnt"]

        # Implicit: shared tags (2+ overlap)
        my_tags = {r["tagID"] for r in conn.execute(
            "SELECT tagID FROM itemTags WHERE itemID = ?", (item_id,)
        ).fetchall()}
        if my_tags:
            placeholders = ",".join("?" * len(my_tags))
            rows = conn.execute(
                f"SELECT itemID, COUNT(*) as cnt FROM itemTags "
                f"WHERE tagID IN ({placeholders}) AND itemID != ? "
                f"GROUP BY itemID HAVING cnt >= 2",
                (*my_tags, item_id),
            ).fetchall()
            for r in rows:
                related_ids[r["itemID"]] = related_ids.get(r["itemID"], 0) + r["cnt"] * 5

        sorted_ids = sorted(related_ids, key=lambda x: related_ids[x], reverse=True)[:limit]
        items = []
        for rid in sorted_ids:
            key_row = conn.execute("SELECT key FROM items WHERE itemID = ?", (rid,)).fetchone()
            if key_row:
                item = self.get_item(key_row["key"])
                if item:
                    items.append(item)
        return items

    @staticmethod
    def _to_bibtex(item: Item) -> str:
        type_map = {"journalArticle": "article", "book": "book", "thesis": "phdthesis"}
        bib_type = type_map.get(item.item_type, "misc")
        cite_key = item.key.lower()
        authors = " and ".join(
            f"{c.last_name}, {c.first_name}" for c in item.creators if c.creator_type == "author"
        )
        lines = [f"@{bib_type}{{{cite_key},"]
        if item.title:
            lines.append(f"  title = {{{item.title}}},")
        if authors:
            lines.append(f"  author = {{{authors}}},")
        if item.date:
            lines.append(f"  year = {{{item.date}}},")
        if item.doi:
            lines.append(f"  doi = {{{item.doi}}},")
        if item.url:
            lines.append(f"  url = {{{item.url}}},")
        lines.append("}")
        return "\n".join(lines)

    @staticmethod
    def _html_to_markdown(html: str) -> str:
        text = re.sub(r"<p>", "", html)
        text = re.sub(r"</p>", "\n", text)
        text = re.sub(r"<br\s*/?>", "\n", text)
        text = re.sub(r"<strong>(.*?)</strong>", r"**\1**", text)
        text = re.sub(r"<em>(.*?)</em>", r"*\1*", text)
        text = re.sub(r"<[^>]+>", "", text)
        return text.strip()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_reader.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add src/zotero_cli_cc/core/ tests/test_reader.py
git commit -m "feat: implement ZoteroReader with SQLite queries for items, search, notes, collections, attachments"
```

---

## Task 6: Output Formatter

**Files:**
- Create: `src/zotero_cli_cc/formatter.py`
- Create: `tests/test_formatter.py`

- [ ] **Step 1: Write tests for formatter**

```python
# tests/test_formatter.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_formatter.py -v`
Expected: FAIL (ImportError)

- [ ] **Step 3: Implement formatter**

```python
# src/zotero_cli_cc/formatter.py
from __future__ import annotations

import json
from dataclasses import asdict
from io import StringIO

from rich.console import Console
from rich.table import Table
from rich.text import Text
from rich.tree import Tree

from zotero_cli_cc.models import Collection, Item, Note


def format_items(items: list[Item], output_json: bool = False) -> str:
    if output_json:
        return json.dumps([asdict(i) for i in items], indent=2, ensure_ascii=False)
    buf = StringIO()
    console = Console(file=buf, force_terminal=False, width=120)
    table = Table(show_header=True, header_style="bold")
    table.add_column("Key", style="cyan", width=10)
    table.add_column("Title", width=50)
    table.add_column("Authors", width=25)
    table.add_column("Year", width=6)
    table.add_column("Type", width=15)
    for item in items:
        authors = ", ".join(c.full_name for c in item.creators[:3])
        if len(item.creators) > 3:
            authors += " et al."
        table.add_row(item.key, item.title, authors, item.date or "", item.item_type)
    console.print(table)
    return buf.getvalue()


def format_item_detail(
    item: Item, notes: list[Note], output_json: bool = False
) -> str:
    if output_json:
        data = asdict(item)
        data["notes"] = [asdict(n) for n in notes]
        return json.dumps(data, indent=2, ensure_ascii=False)
    buf = StringIO()
    console = Console(file=buf, force_terminal=False, width=120)
    console.print(f"[bold cyan]{item.title}[/bold cyan]")
    console.print(f"Key: {item.key}  |  Type: {item.item_type}  |  Date: {item.date or 'N/A'}")
    console.print(f"Authors: {', '.join(c.full_name for c in item.creators)}")
    if item.doi:
        console.print(f"DOI: {item.doi}")
    if item.url:
        console.print(f"URL: {item.url}")
    if item.tags:
        console.print(f"Tags: {', '.join(item.tags)}")
    if item.abstract:
        console.print(f"\n[bold]Abstract:[/bold]\n{item.abstract}")
    if notes:
        console.print(f"\n[bold]Notes ({len(notes)}):[/bold]")
        for n in notes:
            console.print(f"  [{n.key}] {n.content[:200]}")
    return buf.getvalue()


def format_collections(
    collections: list[Collection], output_json: bool = False
) -> str:
    if output_json:
        return json.dumps(
            [_collection_to_dict(c) for c in collections],
            indent=2, ensure_ascii=False,
        )
    buf = StringIO()
    console = Console(file=buf, force_terminal=False, width=120)
    tree = Tree("[bold]Collections[/bold]")
    for c in collections:
        _add_collection_to_tree(tree, c)
    console.print(tree)
    return buf.getvalue()


def format_notes(notes: list[Note], output_json: bool = False) -> str:
    if output_json:
        return json.dumps([asdict(n) for n in notes], indent=2, ensure_ascii=False)
    buf = StringIO()
    console = Console(file=buf, force_terminal=False, width=120)
    for n in notes:
        console.print(f"[bold cyan][{n.key}][/bold cyan]")
        console.print(n.content)
        console.print()
    return buf.getvalue()


def format_error(message: str, output_json: bool = False) -> str:
    if output_json:
        return json.dumps({"error": message}, ensure_ascii=False)
    return f"Error: {message}"


def _collection_to_dict(c: Collection) -> dict:
    return {
        "key": c.key,
        "name": c.name,
        "parent_key": c.parent_key,
        "children": [_collection_to_dict(ch) for ch in c.children],
    }


def _add_collection_to_tree(parent: Tree, c: Collection) -> None:
    node = parent.add(f"[cyan]{c.name}[/cyan] ({c.key})")
    for ch in c.children:
        _add_collection_to_tree(node, ch)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_formatter.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/zotero_cli_cc/formatter.py tests/test_formatter.py
git commit -m "feat: add output formatter with Rich tables and JSON support"
```

---

## Task 7: CLI Skeleton + Config Command

**Files:**
- Create: `src/zotero_cli_cc/cli.py`
- Create: `src/zotero_cli_cc/commands/__init__.py`
- Create: `src/zotero_cli_cc/commands/config.py`
- Create: `tests/test_cli_config.py`

- [ ] **Step 1: Write tests for CLI and config command**

```python
# tests/test_cli_config.py
from click.testing import CliRunner

from zotero_cli_cc.cli import main


def test_cli_version():
    runner = CliRunner()
    result = runner.invoke(main, ["--version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.output


def test_cli_help():
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "search" in result.output


def test_config_init(tmp_path):
    runner = CliRunner()
    config_path = tmp_path / "config.toml"
    result = runner.invoke(
        main,
        ["config", "init", "--config-path", str(config_path)],
        input="12345\nmy-api-key\n",
    )
    assert result.exit_code == 0
    assert config_path.exists()
    content = config_path.read_text()
    assert "12345" in content
    assert "my-api-key" in content


def test_config_show(tmp_path):
    runner = CliRunner()
    config_path = tmp_path / "config.toml"
    config_path.write_text('[zotero]\nlibrary_id = "123"\napi_key = "abc"\n')
    result = runner.invoke(main, ["config", "show", "--config-path", str(config_path)])
    assert result.exit_code == 0
    assert "123" in result.output
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_cli_config.py -v`
Expected: FAIL (ImportError)

- [ ] **Step 3: Implement CLI skeleton**

```python
# src/zotero_cli_cc/cli.py
from __future__ import annotations

import click

from zotero_cli_cc import __version__
from zotero_cli_cc.commands.config import config_group


@click.group()
@click.version_option(version=__version__, prog_name="zot")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
@click.option("--limit", default=50, help="Limit results")
@click.option("--verbose", is_flag=True, help="Verbose output")
@click.pass_context
def main(ctx: click.Context, output_json: bool, limit: int, verbose: bool) -> None:
    """zot — Zotero CLI for Claude Code."""
    ctx.ensure_object(dict)
    ctx.obj["json"] = output_json
    ctx.obj["limit"] = limit
    ctx.obj["verbose"] = verbose


main.add_command(config_group, "config")
```

- [ ] **Step 4: Implement config command**

```python
# src/zotero_cli_cc/commands/__init__.py
```

```python
# src/zotero_cli_cc/commands/config.py
from __future__ import annotations

from pathlib import Path

import click

from zotero_cli_cc.config import AppConfig, load_config, save_config, CONFIG_FILE


@click.group("config")
def config_group() -> None:
    """Manage zot configuration."""
    pass


@config_group.command("init")
@click.option("--config-path", type=click.Path(), default=None, help="Config file path")
def config_init(config_path: str | None) -> None:
    """Initialize configuration interactively."""
    path = Path(config_path) if config_path else CONFIG_FILE
    library_id = click.prompt("Zotero library ID")
    api_key = click.prompt("Zotero API key")
    cfg = AppConfig(library_id=library_id, api_key=api_key)
    save_config(cfg, path)
    click.echo(f"Configuration saved to {path}")


@config_group.command("show")
@click.option("--config-path", type=click.Path(), default=None, help="Config file path")
def config_show(config_path: str | None) -> None:
    """Show current configuration."""
    path = Path(config_path) if config_path else CONFIG_FILE
    cfg = load_config(path)
    click.echo(f"Library ID: {cfg.library_id}")
    click.echo(f"API Key:    {'***' + cfg.api_key[-4:] if len(cfg.api_key) > 4 else '(not set)'}")
    click.echo(f"Data Dir:   {cfg.data_dir or '(auto-detect)'}")
    click.echo(f"Format:     {cfg.default_format}")
    click.echo(f"Limit:      {cfg.default_limit}")
    click.echo(f"Export:     {cfg.default_export_style}")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_cli_config.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add src/zotero_cli_cc/cli.py src/zotero_cli_cc/commands/ tests/test_cli_config.py
git commit -m "feat: add CLI skeleton with Click and config init/show commands"
```

---

## Task 8: P0 Commands — search, list, read, export

**Files:**
- Create: `src/zotero_cli_cc/commands/search.py`
- Create: `src/zotero_cli_cc/commands/list_cmd.py`
- Create: `src/zotero_cli_cc/commands/read.py`
- Create: `src/zotero_cli_cc/commands/export.py`
- Create: `tests/test_cli_p0.py`

- [ ] **Step 1: Write tests for P0 commands**

```python
# tests/test_cli_p0.py
import json
from pathlib import Path

from click.testing import CliRunner

from zotero_cli_cc.cli import main


def _invoke(args: list[str], test_db_path: Path, json_output: bool = False):
    runner = CliRunner()
    base_args = ["--json"] if json_output else []
    config_dir = test_db_path.parent
    env = {"ZOT_DATA_DIR": str(config_dir)}
    return runner.invoke(main, base_args + args, env=env)


class TestSearch:
    def test_search_finds_item(self, test_db_path):
        result = _invoke(["search", "attention"], test_db_path)
        assert result.exit_code == 0
        assert "ATTN001" in result.output

    def test_search_json(self, test_db_path):
        result = _invoke(["search", "attention"], test_db_path, json_output=True)
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert any(i["key"] == "ATTN001" for i in data)

    def test_search_no_results(self, test_db_path):
        result = _invoke(["search", "zzzznonexistent"], test_db_path)
        assert result.exit_code == 0
        assert "No results" in result.output or result.output.strip() == ""

    def test_search_with_collection(self, test_db_path):
        result = _invoke(["search", "", "--collection", "Transformers"], test_db_path, json_output=True)
        data = json.loads(result.output)
        assert all(i["key"] == "ATTN001" for i in data)


class TestList:
    def test_list_all(self, test_db_path):
        result = _invoke(["list"], test_db_path)
        assert result.exit_code == 0
        assert "ATTN001" in result.output

    def test_list_with_collection(self, test_db_path):
        result = _invoke(["list", "--collection", "Machine Learning"], test_db_path, json_output=True)
        data = json.loads(result.output)
        assert len(data) >= 2

    def test_list_with_limit(self, test_db_path):
        result = _invoke(["list", "--limit", "1"], test_db_path, json_output=True)
        data = json.loads(result.output)
        assert len(data) == 1


class TestRead:
    def test_read_item(self, test_db_path):
        result = _invoke(["read", "ATTN001"], test_db_path)
        assert result.exit_code == 0
        assert "Attention Is All You Need" in result.output
        assert "Vaswani" in result.output

    def test_read_json(self, test_db_path):
        result = _invoke(["read", "ATTN001"], test_db_path, json_output=True)
        data = json.loads(result.output)
        assert data["title"] == "Attention Is All You Need"
        assert "notes" in data

    def test_read_nonexistent(self, test_db_path):
        result = _invoke(["read", "NONEXIST"], test_db_path)
        assert result.exit_code == 0
        assert "not found" in result.output.lower() or "Error" in result.output


class TestExport:
    def test_export_bibtex(self, test_db_path):
        result = _invoke(["export", "ATTN001"], test_db_path)
        assert result.exit_code == 0
        assert "@article" in result.output or "@misc" in result.output
        assert "Attention" in result.output

    def test_export_json(self, test_db_path):
        result = _invoke(["export", "ATTN001", "--format", "json"], test_db_path)
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "title" in data
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_cli_p0.py -v`
Expected: FAIL

- [ ] **Step 3: Add env-based data dir override to config**

Add to `src/zotero_cli_cc/config.py`:

```python
import os

def get_data_dir(config: AppConfig) -> Path:
    """Get Zotero data dir: env override > config > default."""
    env_dir = os.environ.get("ZOT_DATA_DIR")
    if env_dir:
        return Path(env_dir)
    return detect_zotero_data_dir(config)
```

- [ ] **Step 4: Implement search command**

```python
# src/zotero_cli_cc/commands/search.py
from __future__ import annotations

import click

from zotero_cli_cc.config import load_config, get_data_dir
from zotero_cli_cc.core.reader import ZoteroReader
from zotero_cli_cc.formatter import format_items


@click.command("search")
@click.argument("query")
@click.option("--collection", default=None, help="Filter by collection name")
@click.pass_context
def search_cmd(ctx: click.Context, query: str, collection: str | None) -> None:
    """Search the Zotero library."""
    cfg = load_config()
    data_dir = get_data_dir(cfg)
    db_path = data_dir / "zotero.sqlite"
    reader = ZoteroReader(db_path)
    try:
        limit = ctx.obj.get("limit", cfg.default_limit)
        result = reader.search(query, collection=collection, limit=limit)
        if not result.items:
            if ctx.obj.get("json"):
                click.echo("[]")
            else:
                click.echo("No results found.")
            return
        click.echo(format_items(result.items, output_json=ctx.obj.get("json", False)))
    finally:
        reader.close()
```

- [ ] **Step 5: Implement list command**

```python
# src/zotero_cli_cc/commands/list_cmd.py
from __future__ import annotations

import click

from zotero_cli_cc.config import load_config, get_data_dir
from zotero_cli_cc.core.reader import ZoteroReader
from zotero_cli_cc.formatter import format_items


@click.command("list")
@click.option("--collection", default=None, help="Filter by collection name")
@click.pass_context
def list_cmd(ctx: click.Context, collection: str | None) -> None:
    """List items in the Zotero library."""
    cfg = load_config()
    data_dir = get_data_dir(cfg)
    db_path = data_dir / "zotero.sqlite"
    reader = ZoteroReader(db_path)
    try:
        limit = ctx.obj.get("limit", cfg.default_limit)
        result = reader.search("", collection=collection, limit=limit)
        click.echo(format_items(result.items, output_json=ctx.obj.get("json", False)))
    finally:
        reader.close()
```

- [ ] **Step 6: Implement read command**

```python
# src/zotero_cli_cc/commands/read.py
from __future__ import annotations

import click

from zotero_cli_cc.config import load_config, get_data_dir
from zotero_cli_cc.core.reader import ZoteroReader
from zotero_cli_cc.formatter import format_item_detail, format_error


@click.command("read")
@click.argument("key")
@click.pass_context
def read_cmd(ctx: click.Context, key: str) -> None:
    """View item details."""
    cfg = load_config()
    data_dir = get_data_dir(cfg)
    db_path = data_dir / "zotero.sqlite"
    reader = ZoteroReader(db_path)
    json_out = ctx.obj.get("json", False)
    try:
        item = reader.get_item(key)
        if item is None:
            click.echo(format_error(f"Item '{key}' not found", output_json=json_out))
            return
        notes = reader.get_notes(key)
        click.echo(format_item_detail(item, notes, output_json=json_out))
    finally:
        reader.close()
```

- [ ] **Step 7: Implement export command**

```python
# src/zotero_cli_cc/commands/export.py
from __future__ import annotations

import json

import click

from zotero_cli_cc.config import load_config, get_data_dir
from zotero_cli_cc.core.reader import ZoteroReader
from zotero_cli_cc.formatter import format_error


@click.command("export")
@click.argument("key")
@click.option("--format", "fmt", default="bibtex", type=click.Choice(["bibtex", "json"]), help="Export format")
@click.pass_context
def export_cmd(ctx: click.Context, key: str, fmt: str) -> None:
    """Export citation."""
    cfg = load_config()
    data_dir = get_data_dir(cfg)
    db_path = data_dir / "zotero.sqlite"
    reader = ZoteroReader(db_path)
    json_out = ctx.obj.get("json", False)
    try:
        if fmt == "json":
            item = reader.get_item(key)
            if item is None:
                click.echo(format_error(f"Item '{key}' not found", output_json=json_out))
                return
            from dataclasses import asdict
            click.echo(json.dumps(asdict(item), indent=2, ensure_ascii=False))
        else:
            result = reader.export_citation(key, fmt=fmt)
            if result is None:
                click.echo(format_error(f"Item '{key}' not found", output_json=json_out))
                return
            click.echo(result)
    finally:
        reader.close()
```

- [ ] **Step 8: Register commands in cli.py**

Update `src/zotero_cli_cc/cli.py` to add:

```python
from zotero_cli_cc.commands.search import search_cmd
from zotero_cli_cc.commands.list_cmd import list_cmd
from zotero_cli_cc.commands.read import read_cmd
from zotero_cli_cc.commands.export import export_cmd

main.add_command(search_cmd, "search")
main.add_command(list_cmd, "list")
main.add_command(read_cmd, "read")
main.add_command(export_cmd, "export")
```

- [ ] **Step 9: Run tests to verify they pass**

Run: `uv run pytest tests/test_cli_p0.py -v`
Expected: All PASS

- [ ] **Step 10: Commit**

```bash
git add src/zotero_cli_cc/commands/ src/zotero_cli_cc/cli.py src/zotero_cli_cc/config.py tests/test_cli_p0.py
git commit -m "feat: implement P0 commands — search, list, read, export"
```

---

## Task 9: P0 Command — note (read + write)

**Files:**
- Create: `src/zotero_cli_cc/commands/note.py`
- Create: `src/zotero_cli_cc/core/writer.py`
- Create: `tests/test_writer.py`
- Create: `tests/test_cli_note.py`

- [ ] **Step 1: Write tests for ZoteroWriter**

```python
# tests/test_writer.py
from unittest.mock import MagicMock, patch

from zotero_cli_cc.core.writer import ZoteroWriter


@patch("zotero_cli_cc.core.writer.zotero.Zotero")
def test_writer_init(mock_zotero_cls):
    writer = ZoteroWriter(library_id="123", api_key="abc")
    mock_zotero_cls.assert_called_once_with("123", "user", "abc")


@patch("zotero_cli_cc.core.writer.zotero.Zotero")
def test_add_note(mock_zotero_cls):
    mock_zot = MagicMock()
    mock_zotero_cls.return_value = mock_zot
    mock_zot.item_template.return_value = {"itemType": "note", "note": "", "parentItem": ""}
    mock_zot.create_items.return_value = {"successful": {"0": {"key": "N1"}}}

    writer = ZoteroWriter(library_id="123", api_key="abc")
    result = writer.add_note("PARENT1", "My note content")
    assert result == "N1"
    mock_zot.create_items.assert_called_once()


@patch("zotero_cli_cc.core.writer.zotero.Zotero")
def test_add_tags(mock_zotero_cls):
    mock_zot = MagicMock()
    mock_zotero_cls.return_value = mock_zot
    mock_zot.item.return_value = {"key": "K1", "data": {"tags": [{"tag": "old"}]}}

    writer = ZoteroWriter(library_id="123", api_key="abc")
    writer.add_tags("K1", ["new1", "new2"])
    mock_zot.update_item.assert_called_once()


@patch("zotero_cli_cc.core.writer.zotero.Zotero")
def test_delete_item(mock_zotero_cls):
    mock_zot = MagicMock()
    mock_zotero_cls.return_value = mock_zot
    mock_zot.item.return_value = {"key": "K1", "data": {"deleted": 0}}

    writer = ZoteroWriter(library_id="123", api_key="abc")
    writer.delete_item("K1")
    mock_zot.delete_item.assert_called_once()


# --- Error-path tests ---

@patch("zotero_cli_cc.core.writer.zotero.Zotero")
def test_add_note_network_error(mock_zotero_cls):
    mock_zot = MagicMock()
    mock_zotero_cls.return_value = mock_zot
    mock_zot.item_template.return_value = {"itemType": "note", "note": "", "parentItem": ""}
    from requests.exceptions import ConnectionError
    mock_zot.create_items.side_effect = ConnectionError("Network unreachable")

    writer = ZoteroWriter(library_id="123", api_key="abc")
    with pytest.raises(ZoteroWriteError, match="Network"):
        writer.add_note("P1", "content")


@patch("zotero_cli_cc.core.writer.zotero.Zotero")
def test_add_note_api_failure(mock_zotero_cls):
    mock_zot = MagicMock()
    mock_zotero_cls.return_value = mock_zot
    mock_zot.item_template.return_value = {"itemType": "note", "note": "", "parentItem": ""}
    mock_zot.create_items.return_value = {"successful": {}, "failed": {"0": {"message": "Bad request"}}}

    writer = ZoteroWriter(library_id="123", api_key="abc")
    with pytest.raises(ZoteroWriteError, match="Bad request"):
        writer.add_note("P1", "content")


@patch("zotero_cli_cc.core.writer.zotero.Zotero")
def test_delete_item_not_found(mock_zotero_cls):
    from pyzotero.zotero_errors import ResourceNotFound
    mock_zot = MagicMock()
    mock_zotero_cls.return_value = mock_zot
    mock_zot.item.side_effect = ResourceNotFound("Not found")

    writer = ZoteroWriter(library_id="123", api_key="abc")
    with pytest.raises(ZoteroWriteError, match="not found"):
        writer.delete_item("NONEXIST")
```

Note: import `pytest` and `ZoteroWriteError` at top of test file:

```python
# tests/test_writer.py
import pytest
from unittest.mock import MagicMock, patch

from zotero_cli_cc.core.writer import ZoteroWriter, ZoteroWriteError
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_writer.py -v`
Expected: FAIL (ImportError)

- [ ] **Step 3: Implement ZoteroWriter**

```python
# src/zotero_cli_cc/core/writer.py
from __future__ import annotations

import logging

from pyzotero import zotero
from pyzotero.zotero_errors import ResourceNotFound
from requests.exceptions import ConnectionError as RequestsConnectionError


SYNC_REMINDER = "Change saved. Run Zotero sync to update local database."

logger = logging.getLogger(__name__)


class ZoteroWriteError(Exception):
    """Raised when a Zotero write operation fails."""
    pass


class ZoteroWriter:
    def __init__(self, library_id: str, api_key: str) -> None:
        self._zot = zotero.Zotero(library_id, "user", api_key)

    def _check_response(self, resp: dict) -> str:
        """Check create response, return key or raise error."""
        if resp.get("successful") and "0" in resp["successful"]:
            return resp["successful"]["0"]["key"]
        failed = resp.get("failed", {})
        if failed:
            msg = failed.get("0", {}).get("message", "Unknown API error")
            raise ZoteroWriteError(f"API error: {msg}")
        raise ZoteroWriteError("Unexpected API response")

    def add_note(self, parent_key: str, content: str) -> str:
        try:
            template = self._zot.item_template("note")
            template["note"] = content
            template["parentItem"] = parent_key
            resp = self._zot.create_items([template])
            return self._check_response(resp)
        except RequestsConnectionError as e:
            raise ZoteroWriteError(f"Network error: {e}") from e

    def update_note(self, note_key: str, content: str) -> None:
        try:
            item = self._zot.item(note_key)
            item["data"]["note"] = content
            self._zot.update_item(item)
        except ResourceNotFound:
            raise ZoteroWriteError(f"Note '{note_key}' not found")
        except RequestsConnectionError as e:
            raise ZoteroWriteError(f"Network error: {e}") from e

    def add_item(self, doi: str | None = None, url: str | None = None) -> str:
        if not doi and not url:
            raise ValueError("Either doi or url must be provided")
        try:
            if doi:
                template = self._zot.item_template("journalArticle")
                template["DOI"] = doi
                resp = self._zot.create_items([template])
                return self._check_response(resp)
            template = self._zot.item_template("webpage")
            template["url"] = url
            resp = self._zot.create_items([template])
            return self._check_response(resp)
        except RequestsConnectionError as e:
            raise ZoteroWriteError(f"Network error: {e}") from e

    def delete_item(self, key: str) -> None:
        try:
            item = self._zot.item(key)
            self._zot.delete_item(item)
        except ResourceNotFound:
            raise ZoteroWriteError(f"Item '{key}' not found")
        except RequestsConnectionError as e:
            raise ZoteroWriteError(f"Network error: {e}") from e

    def add_tags(self, key: str, tags: list[str]) -> None:
        try:
            item = self._zot.item(key)
            existing = [t["tag"] for t in item["data"].get("tags", [])]
            new_tags = [{"tag": t} for t in set(existing + tags)]
            item["data"]["tags"] = new_tags
            self._zot.update_item(item)
        except ResourceNotFound:
            raise ZoteroWriteError(f"Item '{key}' not found")
        except RequestsConnectionError as e:
            raise ZoteroWriteError(f"Network error: {e}") from e

    def remove_tags(self, key: str, tags: list[str]) -> None:
        try:
            item = self._zot.item(key)
            item["data"]["tags"] = [
                t for t in item["data"].get("tags", []) if t["tag"] not in tags
            ]
            self._zot.update_item(item)
        except ResourceNotFound:
            raise ZoteroWriteError(f"Item '{key}' not found")
        except RequestsConnectionError as e:
            raise ZoteroWriteError(f"Network error: {e}") from e

    def create_collection(self, name: str, parent_key: str | None = None) -> str:
        payload = [{"name": name, "parentCollection": parent_key or False}]
        resp = self._zot.create_collections(payload)
        return resp["successful"]["0"]["key"]

    def move_to_collection(self, item_key: str, collection_key: str) -> None:
        self._zot.addto_collection(collection_key, self._zot.item(item_key))
```

- [ ] **Step 4: Run writer tests**

Run: `uv run pytest tests/test_writer.py -v`
Expected: All PASS

- [ ] **Step 5: Write tests for note command**

```python
# tests/test_cli_note.py
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

from click.testing import CliRunner

from zotero_cli_cc.cli import main


def test_note_read(test_db_path):
    runner = CliRunner()
    result = runner.invoke(
        main, ["note", "ATTN001"],
        env={"ZOT_DATA_DIR": str(test_db_path.parent)},
    )
    assert result.exit_code == 0
    assert "transformer architecture" in result.output


def test_note_read_json(test_db_path):
    runner = CliRunner()
    result = runner.invoke(
        main, ["--json", "note", "ATTN001"],
        env={"ZOT_DATA_DIR": str(test_db_path.parent)},
    )
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert len(data) >= 1


@patch("zotero_cli_cc.commands.note.ZoteroWriter")
def test_note_add(mock_writer_cls, test_db_path):
    mock_writer = MagicMock()
    mock_writer_cls.return_value = mock_writer
    mock_writer.add_note.return_value = "NEWNOTE"

    runner = CliRunner()
    result = runner.invoke(
        main,
        ["note", "ATTN001", "--add", "New note"],
        env={
            "ZOT_DATA_DIR": str(test_db_path.parent),
            "ZOT_LIBRARY_ID": "123",
            "ZOT_API_KEY": "abc",
        },
    )
    assert result.exit_code == 0
    mock_writer.add_note.assert_called_once()
```

- [ ] **Step 6: Implement note command**

```python
# src/zotero_cli_cc/commands/note.py
from __future__ import annotations

import os

import click

from zotero_cli_cc.config import load_config, get_data_dir
from zotero_cli_cc.core.reader import ZoteroReader
from zotero_cli_cc.core.writer import ZoteroWriter, SYNC_REMINDER
from zotero_cli_cc.formatter import format_notes, format_error


@click.command("note")
@click.argument("key")
@click.option("--add", "content", default=None, help="Add a new note")
@click.pass_context
def note_cmd(ctx: click.Context, key: str, content: str | None) -> None:
    """View or add notes for an item."""
    cfg = load_config()
    json_out = ctx.obj.get("json", False)

    if content:
        # Write mode
        library_id = os.environ.get("ZOT_LIBRARY_ID", cfg.library_id)
        api_key = os.environ.get("ZOT_API_KEY", cfg.api_key)
        if not library_id or not api_key:
            click.echo(format_error("Write credentials not configured. Run: zot config init", output_json=json_out))
            return
        writer = ZoteroWriter(library_id=library_id, api_key=api_key)
        note_key = writer.add_note(key, content)
        click.echo(f"Note added: {note_key}")
        click.echo(SYNC_REMINDER)
    else:
        # Read mode
        data_dir = get_data_dir(cfg)
        db_path = data_dir / "zotero.sqlite"
        reader = ZoteroReader(db_path)
        try:
            notes = reader.get_notes(key)
            if not notes:
                click.echo(format_error(f"No notes found for '{key}'", output_json=json_out))
                return
            click.echo(format_notes(notes, output_json=json_out))
        finally:
            reader.close()
```

- [ ] **Step 7: Register note command in cli.py**

Add to `src/zotero_cli_cc/cli.py`:

```python
from zotero_cli_cc.commands.note import note_cmd
main.add_command(note_cmd, "note")
```

- [ ] **Step 8: Run all note tests**

Run: `uv run pytest tests/test_cli_note.py tests/test_writer.py -v`
Expected: All PASS

- [ ] **Step 9: Commit**

```bash
git add src/zotero_cli_cc/core/writer.py src/zotero_cli_cc/commands/note.py src/zotero_cli_cc/cli.py tests/test_writer.py tests/test_cli_note.py
git commit -m "feat: implement note command with read (SQLite) and write (Web API) support"
```

---

## Task 10: P1 Commands — add, delete, tag, collection

**Files:**
- Create: `src/zotero_cli_cc/commands/add.py`
- Create: `src/zotero_cli_cc/commands/delete.py`
- Create: `src/zotero_cli_cc/commands/tag.py`
- Create: `src/zotero_cli_cc/commands/collection.py`
- Create: `tests/test_cli_p1.py`

- [ ] **Step 1: Write tests for P1 commands**

```python
# tests/test_cli_p1.py
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

from click.testing import CliRunner

from zotero_cli_cc.cli import main

WRITE_ENV = {"ZOT_LIBRARY_ID": "123", "ZOT_API_KEY": "abc"}


@patch("zotero_cli_cc.commands.add.ZoteroWriter")
def test_add_by_doi(mock_writer_cls):
    mock_writer = MagicMock()
    mock_writer_cls.return_value = mock_writer
    mock_writer.add_item.return_value = "NEW001"

    runner = CliRunner()
    result = runner.invoke(main, ["add", "--doi", "10.1234/test"], env=WRITE_ENV)
    assert result.exit_code == 0
    assert "NEW001" in result.output


@patch("zotero_cli_cc.commands.delete.ZoteroWriter")
def test_delete_with_confirm(mock_writer_cls):
    mock_writer = MagicMock()
    mock_writer_cls.return_value = mock_writer

    runner = CliRunner()
    result = runner.invoke(main, ["delete", "K1", "--yes"], env=WRITE_ENV)
    assert result.exit_code == 0
    mock_writer.delete_item.assert_called_once_with("K1")


@patch("zotero_cli_cc.commands.delete.ZoteroWriter")
def test_delete_without_confirm(mock_writer_cls):
    runner = CliRunner()
    result = runner.invoke(main, ["delete", "K1"], input="n\n", env=WRITE_ENV)
    assert result.exit_code == 0
    mock_writer_cls.return_value.delete_item.assert_not_called()


@patch("zotero_cli_cc.commands.tag.ZoteroWriter")
def test_tag_add(mock_writer_cls):
    mock_writer = MagicMock()
    mock_writer_cls.return_value = mock_writer

    runner = CliRunner()
    result = runner.invoke(main, ["tag", "K1", "--add", "newtag"], env=WRITE_ENV)
    assert result.exit_code == 0
    mock_writer.add_tags.assert_called_once_with("K1", ["newtag"])


def test_tag_list(test_db_path):
    runner = CliRunner()
    result = runner.invoke(
        main, ["tag", "ATTN001"],
        env={"ZOT_DATA_DIR": str(test_db_path.parent)},
    )
    assert result.exit_code == 0
    assert "transformer" in result.output


def test_collection_list(test_db_path):
    runner = CliRunner()
    result = runner.invoke(
        main, ["collection", "list"],
        env={"ZOT_DATA_DIR": str(test_db_path.parent)},
    )
    assert result.exit_code == 0
    assert "Machine Learning" in result.output


@patch("zotero_cli_cc.commands.collection.ZoteroWriter")
def test_collection_create(mock_writer_cls):
    mock_writer = MagicMock()
    mock_writer_cls.return_value = mock_writer
    mock_writer.create_collection.return_value = "NEWCOL"

    runner = CliRunner()
    result = runner.invoke(main, ["collection", "create", "New Col"], env=WRITE_ENV)
    assert result.exit_code == 0
    assert "NEWCOL" in result.output
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_cli_p1.py -v`
Expected: FAIL

- [ ] **Step 3: Implement add command**

```python
# src/zotero_cli_cc/commands/add.py
from __future__ import annotations

import os

import click

from zotero_cli_cc.config import load_config
from zotero_cli_cc.core.writer import ZoteroWriter, SYNC_REMINDER
from zotero_cli_cc.formatter import format_error


@click.command("add")
@click.option("--doi", default=None, help="DOI to add")
@click.option("--url", default=None, help="URL to add")
@click.pass_context
def add_cmd(ctx: click.Context, doi: str | None, url: str | None) -> None:
    """Add an item to the Zotero library."""
    cfg = load_config()
    json_out = ctx.obj.get("json", False)
    library_id = os.environ.get("ZOT_LIBRARY_ID", cfg.library_id)
    api_key = os.environ.get("ZOT_API_KEY", cfg.api_key)
    if not library_id or not api_key:
        click.echo(format_error("Write credentials not configured. Run: zot config init", output_json=json_out))
        return
    if not doi and not url:
        click.echo(format_error("Provide --doi or --url", output_json=json_out))
        return
    writer = ZoteroWriter(library_id=library_id, api_key=api_key)
    key = writer.add_item(doi=doi, url=url)
    click.echo(f"Item added: {key}")
    click.echo(SYNC_REMINDER)
```

- [ ] **Step 4: Implement delete command**

```python
# src/zotero_cli_cc/commands/delete.py
from __future__ import annotations

import os

import click

from zotero_cli_cc.config import load_config
from zotero_cli_cc.core.writer import ZoteroWriter, SYNC_REMINDER
from zotero_cli_cc.formatter import format_error


@click.command("delete")
@click.argument("key")
@click.option("--yes", is_flag=True, help="Skip confirmation")
@click.pass_context
def delete_cmd(ctx: click.Context, key: str, yes: bool) -> None:
    """Delete an item (move to trash)."""
    cfg = load_config()
    json_out = ctx.obj.get("json", False)
    library_id = os.environ.get("ZOT_LIBRARY_ID", cfg.library_id)
    api_key = os.environ.get("ZOT_API_KEY", cfg.api_key)
    if not library_id or not api_key:
        click.echo(format_error("Write credentials not configured. Run: zot config init", output_json=json_out))
        return
    if not yes:
        if not click.confirm(f"Delete item '{key}'?"):
            click.echo("Cancelled.")
            return
    writer = ZoteroWriter(library_id=library_id, api_key=api_key)
    writer.delete_item(key)
    click.echo(f"Item '{key}' moved to trash.")
    click.echo(SYNC_REMINDER)
```

- [ ] **Step 5: Implement tag command**

```python
# src/zotero_cli_cc/commands/tag.py
from __future__ import annotations

import os

import click

from zotero_cli_cc.config import load_config, get_data_dir
from zotero_cli_cc.core.reader import ZoteroReader
from zotero_cli_cc.core.writer import ZoteroWriter, SYNC_REMINDER
from zotero_cli_cc.formatter import format_error


@click.command("tag")
@click.argument("key")
@click.option("--add", "add_tag", default=None, help="Add a tag")
@click.option("--remove", "remove_tag", default=None, help="Remove a tag")
@click.pass_context
def tag_cmd(ctx: click.Context, key: str, add_tag: str | None, remove_tag: str | None) -> None:
    """View or manage tags for an item."""
    cfg = load_config()
    json_out = ctx.obj.get("json", False)

    if add_tag or remove_tag:
        library_id = os.environ.get("ZOT_LIBRARY_ID", cfg.library_id)
        api_key = os.environ.get("ZOT_API_KEY", cfg.api_key)
        if not library_id or not api_key:
            click.echo(format_error("Write credentials not configured. Run: zot config init", output_json=json_out))
            return
        writer = ZoteroWriter(library_id=library_id, api_key=api_key)
        if add_tag:
            writer.add_tags(key, [add_tag])
            click.echo(f"Tag '{add_tag}' added to '{key}'.")
        if remove_tag:
            writer.remove_tags(key, [remove_tag])
            click.echo(f"Tag '{remove_tag}' removed from '{key}'.")
        click.echo(SYNC_REMINDER)
    else:
        data_dir = get_data_dir(cfg)
        db_path = data_dir / "zotero.sqlite"
        reader = ZoteroReader(db_path)
        try:
            item = reader.get_item(key)
            if item is None:
                click.echo(format_error(f"Item '{key}' not found", output_json=json_out))
                return
            if json_out:
                import json
                click.echo(json.dumps(item.tags))
            else:
                click.echo(f"Tags for {key}: {', '.join(item.tags) if item.tags else '(none)'}")
        finally:
            reader.close()
```

- [ ] **Step 6: Implement collection command**

```python
# src/zotero_cli_cc/commands/collection.py
from __future__ import annotations

import os

import click

from zotero_cli_cc.config import load_config, get_data_dir
from zotero_cli_cc.core.reader import ZoteroReader
from zotero_cli_cc.core.writer import ZoteroWriter, SYNC_REMINDER
from zotero_cli_cc.formatter import format_collections, format_items, format_error


@click.group("collection")
def collection_group() -> None:
    """Manage Zotero collections."""
    pass


@collection_group.command("list")
@click.pass_context
def collection_list(ctx: click.Context) -> None:
    """List all collections."""
    cfg = load_config()
    data_dir = get_data_dir(cfg)
    db_path = data_dir / "zotero.sqlite"
    reader = ZoteroReader(db_path)
    try:
        collections = reader.get_collections()
        click.echo(format_collections(collections, output_json=ctx.obj.get("json", False)))
    finally:
        reader.close()


@collection_group.command("items")
@click.argument("key")
@click.pass_context
def collection_items(ctx: click.Context, key: str) -> None:
    """List items in a collection."""
    cfg = load_config()
    data_dir = get_data_dir(cfg)
    db_path = data_dir / "zotero.sqlite"
    reader = ZoteroReader(db_path)
    try:
        items = reader.get_collection_items(key)
        click.echo(format_items(items, output_json=ctx.obj.get("json", False)))
    finally:
        reader.close()


@collection_group.command("create")
@click.argument("name")
@click.option("--parent", default=None, help="Parent collection key")
@click.pass_context
def collection_create(ctx: click.Context, name: str, parent: str | None) -> None:
    """Create a new collection."""
    cfg = load_config()
    json_out = ctx.obj.get("json", False)
    library_id = os.environ.get("ZOT_LIBRARY_ID", cfg.library_id)
    api_key = os.environ.get("ZOT_API_KEY", cfg.api_key)
    if not library_id or not api_key:
        click.echo(format_error("Write credentials not configured. Run: zot config init", output_json=json_out))
        return
    writer = ZoteroWriter(library_id=library_id, api_key=api_key)
    key = writer.create_collection(name, parent_key=parent)
    click.echo(f"Collection created: {key}")
    click.echo(SYNC_REMINDER)
```

- [ ] **Step 7: Register P1 commands in cli.py**

Add to `src/zotero_cli_cc/cli.py`:

```python
from zotero_cli_cc.commands.add import add_cmd
from zotero_cli_cc.commands.delete import delete_cmd
from zotero_cli_cc.commands.tag import tag_cmd
from zotero_cli_cc.commands.collection import collection_group

main.add_command(add_cmd, "add")
main.add_command(delete_cmd, "delete")
main.add_command(tag_cmd, "tag")
main.add_command(collection_group, "collection")
```

- [ ] **Step 8: Run tests**

Run: `uv run pytest tests/test_cli_p1.py -v`
Expected: All PASS

- [ ] **Step 9: Commit**

```bash
git add src/zotero_cli_cc/commands/ src/zotero_cli_cc/cli.py tests/test_cli_p1.py
git commit -m "feat: implement P1 commands — add, delete, tag, collection"
```

---

## Task 11: P1 Command — summarize + P2 Commands — pdf, relate

**Files:**
- Create: `src/zotero_cli_cc/commands/summarize.py`
- Create: `src/zotero_cli_cc/commands/pdf.py`
- Create: `src/zotero_cli_cc/commands/relate.py`
- Create: `src/zotero_cli_cc/core/pdf_extractor.py`
- Create: `tests/test_cli_p2.py`
- Create: `tests/test_pdf_extractor.py`
- Create: `tests/fixtures/test.pdf`

- [ ] **Step 1: Create a test PDF fixture**

```python
# Run this once to create a minimal test PDF
import pymupdf
doc = pymupdf.open()
page = doc.new_page()
page.insert_text((72, 72), "This is a test PDF for zotero-cli-cc.\nPage 1 content.")
doc.save("tests/fixtures/test.pdf")
doc.close()
```

Run: `uv run python -c "import pymupdf; doc = pymupdf.open(); page = doc.new_page(); page.insert_text((72, 72), 'This is a test PDF for zotero-cli-cc.\\nPage 1 content.'); doc.save('tests/fixtures/test.pdf'); doc.close()"`

- [ ] **Step 2: Write tests for PDF extractor**

```python
# tests/test_pdf_extractor.py
from pathlib import Path

import pytest

from zotero_cli_cc.core.pdf_extractor import extract_text_from_pdf

FIXTURES = Path(__file__).parent / "fixtures"


def test_extract_full_pdf():
    text = extract_text_from_pdf(FIXTURES / "test.pdf")
    assert "test PDF" in text


def test_extract_specific_pages():
    text = extract_text_from_pdf(FIXTURES / "test.pdf", pages=(1, 1))
    assert "test PDF" in text


def test_extract_nonexistent_pdf():
    with pytest.raises(FileNotFoundError):
        extract_text_from_pdf(FIXTURES / "nonexistent.pdf")
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/test_pdf_extractor.py -v`
Expected: FAIL (ImportError)

- [ ] **Step 4: Implement PDF extractor**

```python
# src/zotero_cli_cc/core/pdf_extractor.py
from __future__ import annotations

from pathlib import Path

import pymupdf


def extract_text_from_pdf(
    pdf_path: Path,
    pages: tuple[int, int] | None = None,
) -> str:
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")
    doc = pymupdf.open(str(pdf_path))
    try:
        if pages:
            start, end = pages
            page_range = range(start - 1, min(end, len(doc)))
        else:
            page_range = range(len(doc))
        texts = []
        for i in page_range:
            texts.append(doc[i].get_text())
        return "\n".join(texts)
    finally:
        doc.close()
```

- [ ] **Step 5: Run PDF tests**

Run: `uv run pytest tests/test_pdf_extractor.py -v`
Expected: All PASS

- [ ] **Step 6: Write tests for summarize, pdf, relate commands**

```python
# tests/test_cli_p2.py
import json
from pathlib import Path

from click.testing import CliRunner

from zotero_cli_cc.cli import main


def test_summarize(test_db_path):
    runner = CliRunner()
    result = runner.invoke(
        main, ["summarize", "ATTN001"],
        env={"ZOT_DATA_DIR": str(test_db_path.parent)},
    )
    assert result.exit_code == 0
    assert "Attention Is All You Need" in result.output
    assert "Vaswani" in result.output


def test_summarize_json(test_db_path):
    runner = CliRunner()
    result = runner.invoke(
        main, ["--json", "summarize", "ATTN001"],
        env={"ZOT_DATA_DIR": str(test_db_path.parent)},
    )
    data = json.loads(result.output)
    assert data["title"] == "Attention Is All You Need"


def test_relate(test_db_path):
    runner = CliRunner()
    result = runner.invoke(
        main, ["relate", "ATTN001"],
        env={"ZOT_DATA_DIR": str(test_db_path.parent)},
    )
    assert result.exit_code == 0
    # ATTN001 and BERT002 share tags and have explicit relation
    assert "BERT002" in result.output


def test_pdf_no_attachment(test_db_path):
    runner = CliRunner()
    result = runner.invoke(
        main, ["pdf", "DEEP003"],
        env={"ZOT_DATA_DIR": str(test_db_path.parent)},
    )
    assert result.exit_code == 0
    assert "no pdf" in result.output.lower() or "not found" in result.output.lower()
```

- [ ] **Step 7: Implement summarize command**

```python
# src/zotero_cli_cc/commands/summarize.py
from __future__ import annotations

import json

import click

from zotero_cli_cc.config import load_config, get_data_dir
from zotero_cli_cc.core.reader import ZoteroReader
from zotero_cli_cc.formatter import format_error


@click.command("summarize")
@click.argument("key")
@click.pass_context
def summarize_cmd(ctx: click.Context, key: str) -> None:
    """Output a structured summary for Claude Code consumption."""
    cfg = load_config()
    json_out = ctx.obj.get("json", False)
    data_dir = get_data_dir(cfg)
    db_path = data_dir / "zotero.sqlite"
    reader = ZoteroReader(db_path)
    try:
        item = reader.get_item(key)
        if item is None:
            click.echo(format_error(f"Item '{key}' not found", output_json=json_out))
            return
        notes = reader.get_notes(key)
        if json_out:
            data = {
                "title": item.title,
                "authors": [c.full_name for c in item.creators],
                "year": item.date,
                "doi": item.doi,
                "abstract": item.abstract,
                "tags": item.tags,
                "notes": [n.content[:500] for n in notes],
            }
            click.echo(json.dumps(data, indent=2, ensure_ascii=False))
        else:
            click.echo(f"Title: {item.title}")
            click.echo(f"Authors: {', '.join(c.full_name for c in item.creators)}")
            click.echo(f"Year: {item.date or 'N/A'}")
            if item.doi:
                click.echo(f"DOI: {item.doi}")
            if item.abstract:
                click.echo(f"Key findings: {item.abstract}")
            if item.tags:
                click.echo(f"Tags: {', '.join(item.tags)}")
            if notes:
                click.echo(f"Notes ({len(notes)}):")
                for n in notes:
                    click.echo(f"  {n.content[:500]}")
    finally:
        reader.close()
```

- [ ] **Step 8: Implement pdf command**

```python
# src/zotero_cli_cc/commands/pdf.py
from __future__ import annotations

import click

from zotero_cli_cc.config import load_config, get_data_dir
from zotero_cli_cc.core.reader import ZoteroReader
from zotero_cli_cc.core.pdf_extractor import extract_text_from_pdf
from zotero_cli_cc.formatter import format_error


@click.command("pdf")
@click.argument("key")
@click.option("--pages", default=None, help="Page range, e.g. '1-5'")
@click.pass_context
def pdf_cmd(ctx: click.Context, key: str, pages: str | None) -> None:
    """Extract text from the PDF attachment."""
    cfg = load_config()
    json_out = ctx.obj.get("json", False)
    data_dir = get_data_dir(cfg)
    db_path = data_dir / "zotero.sqlite"
    reader = ZoteroReader(db_path)
    try:
        att = reader.get_pdf_attachment(key)
        if att is None:
            click.echo(format_error(f"No PDF attachment found for '{key}'", output_json=json_out))
            return
        pdf_path = data_dir / "storage" / att.key / att.filename
        if not pdf_path.exists():
            click.echo(format_error(f"PDF file not found at {pdf_path}", output_json=json_out))
            return
        page_range = None
        if pages:
            parts = pages.split("-")
            start = int(parts[0])
            end = int(parts[1]) if len(parts) > 1 else start
            page_range = (start, end)
        text = extract_text_from_pdf(pdf_path, pages=page_range)
        if json_out:
            import json
            click.echo(json.dumps({"key": key, "pages": pages, "text": text}, ensure_ascii=False))
        else:
            click.echo(text)
    finally:
        reader.close()
```

- [ ] **Step 9: Implement relate command**

Note: `get_related_items` is already implemented in `ZoteroReader` (Task 5).

```python
# src/zotero_cli_cc/commands/relate.py
from __future__ import annotations

import click

from zotero_cli_cc.config import load_config, get_data_dir
from zotero_cli_cc.core.reader import ZoteroReader
from zotero_cli_cc.formatter import format_items, format_error


@click.command("relate")
@click.argument("key")
@click.pass_context
def relate_cmd(ctx: click.Context, key: str) -> None:
    """Find related items."""
    cfg = load_config()
    json_out = ctx.obj.get("json", False)
    data_dir = get_data_dir(cfg)
    db_path = data_dir / "zotero.sqlite"
    reader = ZoteroReader(db_path)
    try:
        limit = ctx.obj.get("limit", 20)
        items = reader.get_related_items(key, limit=limit)
        if not items:
            click.echo(format_error(f"No related items found for '{key}'", output_json=json_out))
            return
        click.echo(format_items(items, output_json=json_out))
    finally:
        reader.close()
```

- [ ] **Step 10: Register commands in cli.py**

Add to `src/zotero_cli_cc/cli.py`:

```python
from zotero_cli_cc.commands.summarize import summarize_cmd
from zotero_cli_cc.commands.pdf import pdf_cmd
from zotero_cli_cc.commands.relate import relate_cmd

main.add_command(summarize_cmd, "summarize")
main.add_command(pdf_cmd, "pdf")
main.add_command(relate_cmd, "relate")
```

- [ ] **Step 11: Run all tests**

Run: `uv run pytest tests/test_cli_p2.py tests/test_pdf_extractor.py -v`
Expected: All PASS

- [ ] **Step 12: Commit**

```bash
git add src/zotero_cli_cc/commands/ src/zotero_cli_cc/core/ src/zotero_cli_cc/cli.py tests/test_cli_p2.py tests/test_pdf_extractor.py tests/fixtures/test.pdf
git commit -m "feat: implement summarize, pdf, relate commands and PDF extractor"
```

---

## Task 12: Full Integration Test + Final Polish

**Files:**
- Create: `tests/test_integration.py`

- [ ] **Step 1: Write full integration test**

```python
# tests/test_integration.py
"""End-to-end integration tests using the fixture DB."""
import json

from click.testing import CliRunner

from zotero_cli_cc.cli import main


def _run(args, test_db_path, json_out=False):
    runner = CliRunner()
    base = ["--json"] if json_out else []
    return runner.invoke(main, base + args, env={"ZOT_DATA_DIR": str(test_db_path.parent)})


def test_full_read_workflow(test_db_path):
    """Search -> read -> notes -> export -> summarize -> relate."""
    # Search
    r = _run(["search", "transformer"], test_db_path, json_out=True)
    assert r.exit_code == 0
    items = json.loads(r.output)
    assert len(items) >= 1
    key = items[0]["key"]

    # Read
    r = _run(["read", key], test_db_path, json_out=True)
    assert r.exit_code == 0
    detail = json.loads(r.output)
    assert detail["title"]

    # Notes
    r = _run(["note", key], test_db_path)
    assert r.exit_code == 0

    # Export
    r = _run(["export", key], test_db_path)
    assert r.exit_code == 0
    assert "@" in r.output  # BibTeX

    # Summarize
    r = _run(["summarize", key], test_db_path)
    assert r.exit_code == 0
    assert "Title:" in r.output

    # Relate
    r = _run(["relate", key], test_db_path)
    assert r.exit_code == 0


def test_collection_workflow(test_db_path):
    """List collections -> list items in collection."""
    r = _run(["collection", "list"], test_db_path, json_out=True)
    assert r.exit_code == 0
    colls = json.loads(r.output)
    assert len(colls) >= 1

    r = _run(["collection", "items", "COLML01"], test_db_path, json_out=True)
    assert r.exit_code == 0
    items = json.loads(r.output)
    assert len(items) >= 2


def test_version():
    runner = CliRunner()
    r = runner.invoke(main, ["--version"])
    assert r.exit_code == 0
    assert "0.1.0" in r.output
```

- [ ] **Step 2: Run full test suite**

Run: `uv run pytest tests/ -v --tb=short`
Expected: All PASS

- [ ] **Step 3: Run with coverage**

Run: `uv run pytest tests/ --cov=zotero_cli_cc --cov-report=term-missing`
Expected: Coverage report printed, reasonable coverage

- [ ] **Step 4: Test CLI entry point**

Run: `uv run zot --version`
Expected: `zot, version 0.1.0`

Run: `uv run zot --help`
Expected: Help with all commands listed

- [ ] **Step 5: Commit**

```bash
git add tests/test_integration.py
git commit -m "test: add full integration tests for read workflow and collection workflow"
```

---

## Task 13: README

**Files:**
- Create: `README.md`

- [ ] **Step 1: Write README**

```markdown
# zotero-cli-cc

Zotero CLI for Claude Code — fast local reads via SQLite, safe writes via Web API.

## Install

```bash
uv tool install zotero-cli-cc
# or
pip install zotero-cli-cc
```

## Setup

```bash
# Configure Web API credentials (needed for write operations only)
zot config init
```

Read operations work immediately with zero configuration if Zotero data is at the default location (`~/Zotero`).

## Usage

```bash
# Search
zot search "transformer attention"
zot search "BERT" --collection "NLP"

# List
zot list --collection "Machine Learning" --limit 10

# Read details
zot read ATTN001

# Notes
zot note ATTN001                    # View notes
zot note ATTN001 --add "Important"  # Add note (Web API)

# Export citation
zot export ATTN001                  # BibTeX
zot export ATTN001 --format json    # JSON

# Add / Delete
zot add --doi "10.1234/example"
zot delete ATTN001 --yes

# Tags
zot tag ATTN001                     # View tags
zot tag ATTN001 --add "important"   # Add tag (Web API)

# Collections
zot collection list
zot collection items COLML01
zot collection create "New Project"

# Summarize (structured output for Claude Code)
zot summarize ATTN001

# PDF text extraction
zot pdf ATTN001 --pages 1-5

# Related items
zot relate ATTN001

# JSON output
zot --json search "attention"
```

## Architecture

- **Reads**: Direct SQLite access to `~/Zotero/zotero.sqlite` (read-only, offline, fast)
- **Writes**: Zotero Web API via pyzotero (safe, Zotero-aware)
- **PDF**: Direct extraction from `~/Zotero/storage/` via pymupdf

## Environment Variables

| Variable | Purpose |
|----------|---------|
| `ZOT_DATA_DIR` | Override Zotero data directory path |
| `ZOT_LIBRARY_ID` | Override library ID (for write operations) |
| `ZOT_API_KEY` | Override API key (for write operations) |

## License

MIT
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: add README with installation and usage guide"
```
