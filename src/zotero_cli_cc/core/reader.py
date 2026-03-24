from __future__ import annotations

import json
import shutil
import sqlite3
import tempfile
import time
import warnings
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

# Excluded type names (looked up dynamically per database)
_EXCLUDED_TYPE_NAMES = ("attachment", "note", "annotation")

# Tested schema version range (Zotero 6–8)
MIN_SCHEMA_VERSION = 100
MAX_SCHEMA_VERSION = 200


class ZoteroReader:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._conn: sqlite3.Connection | None = None
        self._tmp_dir: Path | None = None
        self._excluded_sql: str | None = None
        self._excluded_ids: tuple[int, ...] | None = None
        self._tmp_dir_obj: tempfile.TemporaryDirectory[str] | None = None

    def _connect(self) -> sqlite3.Connection:
        if self._conn is not None:
            return self._conn
        for attempt in range(MAX_RETRIES):
            try:
                conn = sqlite3.connect(
                    f"file:{self._db_path}?mode=ro",
                    uri=True,
                    timeout=5.0,
                )
                conn.row_factory = sqlite3.Row
                # Test that we can actually query
                conn.execute("SELECT 1 FROM items LIMIT 1")
                self._conn = conn
                return conn
            except sqlite3.OperationalError:
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY)
                    continue
                # Fallback: copy DB to temp file
                return self._connect_from_copy()
        raise sqlite3.OperationalError(f"Failed to connect to {self._db_path} after {MAX_RETRIES} retries")

    def _get_excluded_ids(self) -> tuple[int, ...]:
        """Look up excluded type IDs by name (cached after first call)."""
        if self._excluded_ids is not None:
            return self._excluded_ids
        conn = self._connect()
        placeholders = ",".join("?" * len(_EXCLUDED_TYPE_NAMES))
        rows = conn.execute(
            f"SELECT itemTypeID FROM itemTypes WHERE typeName IN ({placeholders})",
            _EXCLUDED_TYPE_NAMES,
        ).fetchall()
        self._excluded_ids = tuple(r["itemTypeID"] for r in rows) if rows else (-1,)
        return self._excluded_ids

    def _get_excluded_sql(self) -> str:
        """Build SQL fragment with literal IDs (for simple string concatenation)."""
        if self._excluded_sql is not None:
            return self._excluded_sql
        ids = self._get_excluded_ids()
        self._excluded_sql = f"NOT IN ({','.join(str(i) for i in ids)})"
        return self._excluded_sql

    def _excluded_filter(self) -> tuple[str, tuple[int, ...]]:
        """Return (SQL fragment with ? placeholders, parameter tuple) for excluded types."""
        ids = self._get_excluded_ids()
        ph = ",".join("?" * len(ids))
        return f"NOT IN ({ph})", ids

    def _connect_from_copy(self) -> sqlite3.Connection:
        """Copy DB files to temp dir to avoid WAL locks."""
        self._tmp_dir_obj = tempfile.TemporaryDirectory()
        self._tmp_dir = Path(self._tmp_dir_obj.name)
        tmp = self._tmp_dir / "zotero.sqlite"
        shutil.copy2(self._db_path, tmp)
        wal = self._db_path.with_suffix(".sqlite-wal")
        shm = self._db_path.with_suffix(".sqlite-shm")
        if wal.exists():
            shutil.copy2(wal, tmp.with_suffix(".sqlite-wal"))
        if shm.exists():
            shutil.copy2(shm, tmp.with_suffix(".sqlite-shm"))
        conn = sqlite3.connect(str(tmp), timeout=5.0)
        conn.row_factory = sqlite3.Row
        self._conn = conn
        return conn

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None
        if hasattr(self, "_tmp_dir_obj") and self._tmp_dir_obj is not None:
            self._tmp_dir_obj.cleanup()
            self._tmp_dir_obj = None
            self._tmp_dir = None

    def __enter__(self) -> ZoteroReader:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        self.close()

    def get_schema_version(self) -> int | None:
        conn = self._connect()
        row = conn.execute("SELECT version FROM version WHERE schema = 'userdata'").fetchone()
        return row["version"] if row else None

    def check_schema_compatibility(self) -> None:
        version = self.get_schema_version()
        if version and (version < MIN_SCHEMA_VERSION or version > MAX_SCHEMA_VERSION):
            warnings.warn(
                f"Zotero schema version {version} is outside the tested range (100-200). "
                "Some queries may not work correctly.",
                stacklevel=2,
            )

    def get_item(self, key: str) -> Item | None:
        conn = self._connect()
        row = conn.execute(
            "SELECT itemID, itemTypeID, key, dateAdded, dateModified "
            "FROM items WHERE key = ? AND itemTypeID " + self._get_excluded_sql(),
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
            extra={k: v for k, v in fields.items() if k not in ("title", "abstractNote", "date", "url", "DOI")},
        )

    def search(
        self,
        query: str,
        collection: str | None = None,
        item_type: str | None = None,
        sort: str | None = None,
        direction: str = "desc",
        limit: int = 50,
        offset: int = 0,
    ) -> SearchResult:
        conn = self._connect()
        item_ids: set[int] = set()
        excl_sql, excl_params = self._excluded_filter()

        if query:
            like = f"%{query}%"
            # Search titles and abstracts
            rows = conn.execute(
                "SELECT DISTINCT i.itemID FROM items i "
                "JOIN itemData id ON i.itemID = id.itemID "
                "JOIN itemDataValues iv ON id.valueID = iv.valueID "
                f"WHERE iv.value LIKE ? AND i.itemTypeID {excl_sql}",
                (like, *excl_params),
            ).fetchall()
            item_ids.update(r["itemID"] for r in rows)

            # Search creators
            rows = conn.execute(
                "SELECT DISTINCT ic.itemID FROM itemCreators ic "
                "JOIN creators c ON ic.creatorID = c.creatorID "
                "JOIN items i ON ic.itemID = i.itemID "
                "WHERE (c.firstName LIKE ? OR c.lastName LIKE ?) "
                f"AND i.itemTypeID {excl_sql}",
                (like, like, *excl_params),
            ).fetchall()
            item_ids.update(r["itemID"] for r in rows)

            # Search tags
            rows = conn.execute(
                "SELECT DISTINCT it.itemID FROM itemTags it "
                "JOIN tags t ON it.tagID = t.tagID "
                "JOIN items i ON it.itemID = i.itemID "
                f"WHERE t.name LIKE ? AND i.itemTypeID {excl_sql}",
                (like, *excl_params),
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
            rows = conn.execute(
                f"SELECT itemID FROM items WHERE itemTypeID {excl_sql}",
                excl_params,
            ).fetchall()
            item_ids.update(r["itemID"] for r in rows)

        # Filter by collection (accepts key or name)
        if collection:
            col_row = conn.execute(
                "SELECT collectionID FROM collections WHERE key = ? OR collectionName = ?",
                (collection, collection),
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

        # Filter by item type
        if item_type:
            type_row = conn.execute(
                "SELECT itemTypeID FROM itemTypes WHERE typeName = ?",
                (item_type,),
            ).fetchone()
            if type_row:
                typed_items = conn.execute(
                    "SELECT itemID FROM items WHERE itemTypeID = ? AND itemID IN ({})".format(
                        ",".join("?" * len(item_ids))
                    ),
                    (type_row["itemTypeID"], *item_ids),
                ).fetchall()
                item_ids = {r["itemID"] for r in typed_items}
            else:
                item_ids = set()

        # Resolve items in batch
        total = len(item_ids)

        if sort and item_ids:
            dir_sql = "DESC" if direction == "desc" else "ASC"
            ph = ",".join("?" * len(item_ids))
            id_list = list(item_ids)

            if sort in ("dateAdded", "dateModified"):
                rows = conn.execute(
                    f"SELECT itemID FROM items WHERE itemID IN ({ph}) ORDER BY {sort} {dir_sql} LIMIT ? OFFSET ?",
                    (*id_list, limit, offset),
                ).fetchall()
                target_ids = [r["itemID"] for r in rows]
            elif sort == "title":
                title_field = conn.execute("SELECT fieldID FROM fields WHERE fieldName = 'title'").fetchone()
                fid = title_field["fieldID"] if title_field else 4
                rows = conn.execute(
                    f"SELECT i.itemID FROM items i "
                    f"LEFT JOIN itemData id_t ON i.itemID = id_t.itemID AND id_t.fieldID = ? "
                    f"LEFT JOIN itemDataValues iv_t ON id_t.valueID = iv_t.valueID "
                    f"WHERE i.itemID IN ({ph}) "
                    f"ORDER BY COALESCE(iv_t.value, '') COLLATE NOCASE {dir_sql} LIMIT ? OFFSET ?",
                    (fid, *id_list, limit, offset),
                ).fetchall()
                target_ids = [r["itemID"] for r in rows]
            elif sort == "creator":
                rows = conn.execute(
                    f"SELECT i.itemID FROM items i "
                    f"LEFT JOIN itemCreators ic ON i.itemID = ic.itemID AND ic.orderIndex = 0 "
                    f"LEFT JOIN creators c ON ic.creatorID = c.creatorID "
                    f"WHERE i.itemID IN ({ph}) "
                    f"ORDER BY COALESCE(c.lastName, '') COLLATE NOCASE {dir_sql} LIMIT ? OFFSET ?",
                    (*id_list, limit, offset),
                ).fetchall()
                target_ids = [r["itemID"] for r in rows]
            else:
                target_ids = sorted(item_ids)[offset : offset + limit]
        else:
            target_ids = sorted(item_ids)[offset : offset + limit]

        items = self._get_items_batch(conn, target_ids) if target_ids else []

        return SearchResult(items=items, total=total, query=query)

    def get_recent_items(
        self,
        since: str,
        sort: str = "dateAdded",
        limit: int = 50,
    ) -> list[Item]:
        """Return items added or modified since the given timestamp."""
        conn = self._connect()
        excl_sql, excl_params = self._excluded_filter()
        col = "dateModified" if sort == "dateModified" else "dateAdded"
        rows = conn.execute(
            f"SELECT itemID FROM items WHERE {col} >= ? AND itemTypeID {excl_sql} ORDER BY {col} DESC LIMIT ?",
            (since, *excl_params, limit),
        ).fetchall()
        item_ids = [r["itemID"] for r in rows]
        return self._get_items_batch(conn, item_ids) if item_ids else []

    def get_trash_items(self, limit: int = 50) -> list[Item]:
        """Return items in the trash, ordered by deletion date (newest first)."""
        conn = self._connect()
        excl_sql, excl_params = self._excluded_filter()
        rows = conn.execute(
            f"SELECT i.itemID FROM items i "
            f"JOIN deletedItems d ON i.itemID = d.itemID "
            f"WHERE i.itemTypeID {excl_sql} "
            f"ORDER BY d.dateDeleted DESC LIMIT ?",
            (*excl_params, limit),
        ).fetchall()
        item_ids = [r["itemID"] for r in rows]
        return self._get_items_batch(conn, item_ids) if item_ids else []

    def get_notes(self, key: str) -> list[Note]:
        conn = self._connect()
        parent = conn.execute("SELECT itemID FROM items WHERE key = ?", (key,)).fetchone()
        if parent is None:
            return []
        rows = conn.execute(
            "SELECT i.key, n.note FROM itemNotes n JOIN items i ON n.itemID = i.itemID WHERE n.parentItemID = ?",
            (parent["itemID"],),
        ).fetchall()
        notes = []
        for r in rows:
            content = self._html_to_markdown(r["note"] or "")
            tags = self._get_item_tags(
                conn,
                conn.execute("SELECT itemID FROM items WHERE key = ?", (r["key"],)).fetchone()["itemID"],
            )
            notes.append(Note(key=r["key"], parent_key=key, content=content, tags=tags))
        return notes

    def get_collections(self) -> list[Collection]:
        conn = self._connect()
        rows = conn.execute("SELECT collectionID, collectionName, parentCollectionID, key FROM collections").fetchall()
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
            "WHERE ci.collectionID = ? AND i.itemTypeID " + self._get_excluded_sql(),
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
        parent = conn.execute("SELECT itemID FROM items WHERE key = ?", (key,)).fetchone()
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
            attachments.append(
                Attachment(
                    key=r["key"],
                    parent_key=key,
                    filename=filename,
                    content_type=r["contentType"] or "",
                    path=None,
                )
            )
        return attachments

    def get_pdf_attachment(self, key: str) -> Attachment | None:
        for att in self.get_attachments(key):
            if att.content_type == "application/pdf":
                return att
        return None

    def get_stats(self) -> dict:
        """Return library statistics."""
        conn = self._connect()
        # Total items (excluding attachments and notes)
        total = conn.execute(
            "SELECT COUNT(*) as cnt FROM items WHERE itemTypeID " + self._get_excluded_sql()
        ).fetchone()["cnt"]

        # Items by type
        type_rows = conn.execute(
            "SELECT t.typeName, COUNT(*) as cnt FROM items i "
            "JOIN itemTypes t ON i.itemTypeID = t.itemTypeID "
            "WHERE i.itemTypeID " + self._get_excluded_sql() + " "
            "GROUP BY t.typeName ORDER BY cnt DESC"
        ).fetchall()
        by_type = {r["typeName"]: r["cnt"] for r in type_rows}

        # Top tags
        tag_rows = conn.execute(
            "SELECT t.name, COUNT(*) as cnt FROM itemTags it "
            "JOIN tags t ON it.tagID = t.tagID "
            "GROUP BY t.name ORDER BY cnt DESC LIMIT 20"
        ).fetchall()
        top_tags = {r["name"]: r["cnt"] for r in tag_rows}

        # Collections with item counts
        coll_rows = conn.execute(
            "SELECT c.collectionName, COUNT(ci.itemID) as cnt "
            "FROM collections c "
            "LEFT JOIN collectionItems ci ON c.collectionID = ci.collectionID "
            "GROUP BY c.collectionName ORDER BY cnt DESC"
        ).fetchall()
        collections = {r["collectionName"]: r["cnt"] for r in coll_rows}

        # Attachments
        pdf_count = conn.execute(
            "SELECT COUNT(*) as cnt FROM itemAttachments WHERE contentType = 'application/pdf'"
        ).fetchone()["cnt"]

        # Notes count
        notes_count = conn.execute("SELECT COUNT(*) as cnt FROM itemNotes").fetchone()["cnt"]

        return {
            "total_items": total,
            "by_type": by_type,
            "top_tags": top_tags,
            "collections": collections,
            "pdf_attachments": pdf_count,
            "notes": notes_count,
        }

    def export_citation(self, key: str, fmt: str = "bibtex") -> str | None:
        item = self.get_item(key)
        if item is None:
            return None
        if fmt == "bibtex":
            return self._to_bibtex(item)
        if fmt in ("csl", "csl-json", "json"):
            return self._to_csl_json(item)
        if fmt == "ris":
            return self._to_ris(item)
        return None

    def get_related_items(self, key: str, limit: int = 20) -> list[Item]:
        conn = self._connect()
        parent = conn.execute("SELECT itemID FROM items WHERE key = ?", (key,)).fetchone()
        if parent is None:
            return []
        item_id = parent["itemID"]
        related_ids: dict[int, int] = {}

        # Explicit relations
        rows = conn.execute(
            "SELECT object FROM itemRelations WHERE itemID = ? AND predicateID = 1",
            (item_id,),
        ).fetchall()
        for r in rows:
            obj = r["object"]
            rel_key = obj.rsplit("/", 1)[-1] if "/" in obj else obj
            rel_row = conn.execute("SELECT itemID FROM items WHERE key = ?", (rel_key,)).fetchone()
            if rel_row:
                related_ids[rel_row["itemID"]] = related_ids.get(rel_row["itemID"], 0) + 100

        # Implicit: shared collections
        my_cols = {
            r["collectionID"]
            for r in conn.execute("SELECT collectionID FROM collectionItems WHERE itemID = ?", (item_id,)).fetchall()
        }
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
        my_tags = {
            r["tagID"] for r in conn.execute("SELECT tagID FROM itemTags WHERE itemID = ?", (item_id,)).fetchall()
        }
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

    # --- Private helpers ---

    def _get_items_batch(self, conn: sqlite3.Connection, item_ids: list[int]) -> list[Item]:
        """Resolve multiple item IDs to Items using bulk queries instead of N+1."""
        if not item_ids:
            return []

        placeholders = ",".join("?" * len(item_ids))

        # Fetch base item rows
        rows = conn.execute(
            f"SELECT itemID, itemTypeID, key, dateAdded, dateModified "
            f"FROM items WHERE itemID IN ({placeholders}) AND itemTypeID {self._get_excluded_sql()}",
            item_ids,
        ).fetchall()
        if not rows:
            return []

        id_to_row = {r["itemID"]: r for r in rows}
        valid_ids = list(id_to_row.keys())
        valid_ph = ",".join("?" * len(valid_ids))

        # Batch fetch item types
        type_ids = list({r["itemTypeID"] for r in rows})
        type_ph = ",".join("?" * len(type_ids))
        type_rows = conn.execute(
            f"SELECT itemTypeID, typeName FROM itemTypes WHERE itemTypeID IN ({type_ph})",
            type_ids,
        ).fetchall()
        type_map = {r["itemTypeID"]: r["typeName"] for r in type_rows}

        # Batch fetch fields
        field_rows = conn.execute(
            f"SELECT id.itemID, f.fieldName, iv.value FROM itemData id "
            f"JOIN fields f ON id.fieldID = f.fieldID "
            f"JOIN itemDataValues iv ON id.valueID = iv.valueID "
            f"WHERE id.itemID IN ({valid_ph})",
            valid_ids,
        ).fetchall()
        fields_map: dict[int, dict[str, str]] = {}
        for r in field_rows:
            fields_map.setdefault(r["itemID"], {})[r["fieldName"]] = r["value"]

        # Batch fetch creators
        creator_rows = conn.execute(
            f"SELECT ic.itemID, c.firstName, c.lastName, ct.creatorType "
            f"FROM itemCreators ic "
            f"JOIN creators c ON ic.creatorID = c.creatorID "
            f"JOIN creatorTypes ct ON ic.creatorTypeID = ct.creatorTypeID "
            f"WHERE ic.itemID IN ({valid_ph}) ORDER BY ic.itemID, ic.orderIndex",
            valid_ids,
        ).fetchall()
        creators_map: dict[int, list[Creator]] = {}
        for r in creator_rows:
            creators_map.setdefault(r["itemID"], []).append(
                Creator(r["firstName"] or "", r["lastName"] or "", r["creatorType"])
            )

        # Batch fetch tags
        tag_rows = conn.execute(
            f"SELECT it.itemID, t.name FROM itemTags it "
            f"JOIN tags t ON it.tagID = t.tagID "
            f"WHERE it.itemID IN ({valid_ph})",
            valid_ids,
        ).fetchall()
        tags_map: dict[int, list[str]] = {}
        for r in tag_rows:
            tags_map.setdefault(r["itemID"], []).append(r["name"])

        # Batch fetch collections
        coll_rows = conn.execute(
            f"SELECT ci.itemID, c.key FROM collectionItems ci "
            f"JOIN collections c ON ci.collectionID = c.collectionID "
            f"WHERE ci.itemID IN ({valid_ph})",
            valid_ids,
        ).fetchall()
        colls_map: dict[int, list[str]] = {}
        for r in coll_rows:
            colls_map.setdefault(r["itemID"], []).append(r["key"])

        # Assemble items in original order
        items: list[Item] = []
        for item_id in item_ids:
            if item_id not in id_to_row:
                continue
            row = id_to_row[item_id]
            fields = fields_map.get(item_id, {})
            items.append(
                Item(
                    key=row["key"],
                    item_type=type_map.get(row["itemTypeID"], "unknown"),
                    title=fields.get("title", ""),
                    creators=creators_map.get(item_id, []),
                    abstract=fields.get("abstractNote"),
                    date=fields.get("date"),
                    url=fields.get("url"),
                    doi=fields.get("DOI"),
                    tags=tags_map.get(item_id, []),
                    collections=colls_map.get(item_id, []),
                    date_added=row["dateAdded"],
                    date_modified=row["dateModified"],
                    extra={k: v for k, v in fields.items() if k not in ("title", "abstractNote", "date", "url", "DOI")},
                )
            )
        return items

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
        return [Creator(r["firstName"] or "", r["lastName"] or "", r["creatorType"]) for r in rows]

    def _get_item_tags(self, conn: sqlite3.Connection, item_id: int) -> list[str]:
        rows = conn.execute(
            "SELECT t.name FROM itemTags it JOIN tags t ON it.tagID = t.tagID WHERE it.itemID = ?",
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

    @staticmethod
    def _escape_bibtex(value: str) -> str:
        """Escape special LaTeX/BibTeX characters in a field value."""
        for char, escaped in (("&", r"\&"), ("%", r"\%"), ("#", r"\#"), ("_", r"\_")):
            value = value.replace(char, escaped)
        return value

    @staticmethod
    def _to_bibtex(item: Item) -> str:
        type_map = {"journalArticle": "article", "book": "book", "thesis": "phdthesis"}
        bib_type = type_map.get(item.item_type, "misc")
        cite_key = item.key.lower()
        esc = ZoteroReader._escape_bibtex
        authors = " and ".join(
            f"{esc(c.last_name)}, {esc(c.first_name)}" for c in item.creators if c.creator_type == "author"
        )
        lines = [f"@{bib_type}{{{cite_key},"]
        if item.title:
            lines.append(f"  title = {{{esc(item.title)}}},")
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
    def _to_csl_json(item: Item) -> str:
        """Convert an Item to CSL-JSON format (single item, not array)."""
        type_map = {
            "journalArticle": "article-journal",
            "book": "book",
            "bookSection": "chapter",
            "conferencePaper": "paper-conference",
            "thesis": "thesis",
            "report": "report",
            "webpage": "webpage",
            "preprint": "article",
        }
        csl: dict = {
            "id": item.key,
            "type": type_map.get(item.item_type, "article"),
            "title": item.title,
        }
        if item.creators:
            csl["author"] = [
                {"family": c.last_name, "given": c.first_name} for c in item.creators if c.creator_type == "author"
            ]
        if item.date:
            csl["issued"] = {"raw": item.date}
        if item.abstract:
            csl["abstract"] = item.abstract
        if item.doi:
            csl["DOI"] = item.doi
        if item.url:
            csl["URL"] = item.url
        return json.dumps(csl, indent=2, ensure_ascii=False)

    @staticmethod
    def _to_ris(item: Item) -> str:
        """Convert an Item to RIS format."""
        type_map = {
            "journalArticle": "JOUR",
            "book": "BOOK",
            "bookSection": "CHAP",
            "conferencePaper": "CONF",
            "thesis": "THES",
            "report": "RPRT",
            "webpage": "ELEC",
            "preprint": "JOUR",
            "patent": "PAT",
            "newspaperArticle": "NEWS",
            "magazineArticle": "MGZN",
        }
        lines = [f"TY  - {type_map.get(item.item_type, 'GEN')}"]
        if item.title:
            lines.append(f"TI  - {item.title}")
        for c in item.creators:
            if c.creator_type == "author":
                lines.append(f"AU  - {c.last_name}, {c.first_name}")
        if item.date:
            lines.append(f"PY  - {item.date}")
        if item.abstract:
            lines.append(f"AB  - {item.abstract}")
        if item.doi:
            lines.append(f"DO  - {item.doi}")
        if item.url:
            lines.append(f"UR  - {item.url}")
        for tag in item.tags:
            lines.append(f"KW  - {tag}")
        lines.append("ER  - ")
        return "\n".join(lines)

    @staticmethod
    def _html_to_markdown(html: str) -> str:
        from markdownify import markdownify as md

        return md(html, strip=["img"]).strip()
