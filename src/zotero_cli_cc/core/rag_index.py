from __future__ import annotations

import sqlite3
import struct
from pathlib import Path


class RagIndex:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path))
        self._conn.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS chunks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_key TEXT NOT NULL,
                source TEXT NOT NULL,
                content TEXT NOT NULL,
                doc_len INTEGER NOT NULL DEFAULT 0,
                embedding BLOB
            );
            CREATE TABLE IF NOT EXISTS bm25_terms (
                term TEXT NOT NULL,
                chunk_id INTEGER NOT NULL,
                tf REAL NOT NULL,
                FOREIGN KEY (chunk_id) REFERENCES chunks(id)
            );
            CREATE INDEX IF NOT EXISTS idx_bm25_term ON bm25_terms(term);
            CREATE INDEX IF NOT EXISTS idx_bm25_chunk ON bm25_terms(chunk_id);
            CREATE INDEX IF NOT EXISTS idx_chunks_item ON chunks(item_key);
            CREATE TABLE IF NOT EXISTS index_meta (
                key TEXT PRIMARY KEY,
                value TEXT
            );
        """)
        self._conn.commit()

    def insert_chunk(self, item_key: str, source: str, content: str, doc_len: int = 0) -> int:
        cur = self._conn.execute(
            "INSERT INTO chunks (item_key, source, content, doc_len) VALUES (?, ?, ?, ?)",
            (item_key, source, content, doc_len),
        )
        self._conn.commit()
        return cur.lastrowid  # type: ignore[return-value]

    def insert_chunk_no_commit(self, item_key: str, source: str, content: str, doc_len: int = 0) -> int:
        cur = self._conn.execute(
            "INSERT INTO chunks (item_key, source, content, doc_len) VALUES (?, ?, ?, ?)",
            (item_key, source, content, doc_len),
        )
        return cur.lastrowid  # type: ignore[return-value]

    def insert_bm25_terms(self, chunk_id: int, term_tfs: dict[str, float]) -> None:
        self._conn.executemany(
            "INSERT INTO bm25_terms (term, chunk_id, tf) VALUES (?, ?, ?)",
            [(term, chunk_id, tf) for term, tf in term_tfs.items()],
        )

    def insert_bm25_terms_no_commit(self, chunk_id: int, term_tfs: dict[str, float]) -> None:
        self._conn.executemany(
            "INSERT INTO bm25_terms (term, chunk_id, tf) VALUES (?, ?, ?)",
            [(term, chunk_id, tf) for term, tf in term_tfs.items()],
        )

    def commit(self) -> None:
        self._conn.commit()

    def get_all_chunks(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT id, item_key, source, content, doc_len FROM chunks"
        ).fetchall()
        return [dict(r) for r in rows]

    def get_bm25_terms_for_chunk(self, chunk_id: int) -> dict[str, float]:
        rows = self._conn.execute(
            "SELECT term, tf FROM bm25_terms WHERE chunk_id = ?", (chunk_id,)
        ).fetchall()
        return {r["term"]: r["tf"] for r in rows}

    def get_bm25_terms_bulk(self, chunk_ids: list[int]) -> dict[int, dict[str, float]]:
        if not chunk_ids:
            return {}
        placeholders = ",".join("?" * len(chunk_ids))
        rows = self._conn.execute(
            f"SELECT chunk_id, term, tf FROM bm25_terms WHERE chunk_id IN ({placeholders})",
            chunk_ids,
        ).fetchall()
        result: dict[int, dict[str, float]] = {cid: {} for cid in chunk_ids}
        for r in rows:
            result[r["chunk_id"]][r["term"]] = r["tf"]
        return result

    def get_indexed_keys(self) -> set[str]:
        rows = self._conn.execute("SELECT DISTINCT item_key FROM chunks").fetchall()
        return {r["item_key"] for r in rows}

    def set_meta(self, key: str, value: str) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO index_meta (key, value) VALUES (?, ?)", (key, value)
        )
        self._conn.commit()

    def get_meta(self, key: str) -> str | None:
        row = self._conn.execute(
            "SELECT value FROM index_meta WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row else None

    def set_embedding(self, chunk_id: int, embedding: list[float]) -> None:
        blob = struct.pack(f"{len(embedding)}f", *embedding)
        self._conn.execute(
            "UPDATE chunks SET embedding = ? WHERE id = ?", (blob, chunk_id)
        )
        self._conn.commit()

    def set_embeddings_bulk(self, chunk_ids: list[int], embeddings: list[list[float]]) -> None:
        for chunk_id, embedding in zip(chunk_ids, embeddings):
            blob = struct.pack(f"{len(embedding)}f", *embedding)
            self._conn.execute(
                "UPDATE chunks SET embedding = ? WHERE id = ?", (blob, chunk_id)
            )
        self._conn.commit()

    def get_embedding(self, chunk_id: int) -> list[float]:
        row = self._conn.execute(
            "SELECT embedding FROM chunks WHERE id = ?", (chunk_id,)
        ).fetchone()
        if row is None or row["embedding"] is None:
            return []
        blob = row["embedding"]
        count = len(blob) // 4
        return list(struct.unpack(f"{count}f", blob))

    def get_all_embeddings(self) -> list[tuple[int, list[float]]]:
        rows = self._conn.execute(
            "SELECT id, embedding FROM chunks WHERE embedding IS NOT NULL"
        ).fetchall()
        result = []
        for r in rows:
            count = len(r["embedding"]) // 4
            vec = list(struct.unpack(f"{count}f", r["embedding"]))
            result.append((r["id"], vec))
        return result

    def clear(self) -> None:
        self._conn.executescript(
            "DELETE FROM bm25_terms; DELETE FROM chunks; DELETE FROM index_meta;"
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()