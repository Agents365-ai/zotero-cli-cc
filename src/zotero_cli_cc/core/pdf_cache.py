from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from platformdirs import user_cache_dir

DEFAULT_CACHE_PATH = Path(user_cache_dir("zot")) / "pdf_cache.sqlite"


class PdfCache:
    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path or DEFAULT_CACHE_PATH
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path))
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS pdf_cache ("
            "  pdf_path TEXT PRIMARY KEY,"
            "  mtime REAL NOT NULL,"
            "  content TEXT NOT NULL,"
            "  extracted_at TEXT NOT NULL"
            ")"
        )
        self._conn.commit()

    def get(self, pdf_path: Path) -> str | None:
        if not pdf_path.exists():
            return None
        current_mtime = pdf_path.stat().st_mtime
        row = self._conn.execute(
            "SELECT content, mtime FROM pdf_cache WHERE pdf_path = ?",
            (str(pdf_path),),
        ).fetchone()
        if row is None:
            return None
        if abs(row[1] - current_mtime) > 0.001:
            return None  # stale
        return row[0]

    def put(self, pdf_path: Path, content: str) -> None:
        mtime = pdf_path.stat().st_mtime
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            "INSERT OR REPLACE INTO pdf_cache (pdf_path, mtime, content, extracted_at) "
            "VALUES (?, ?, ?, ?)",
            (str(pdf_path), mtime, content, now),
        )
        self._conn.commit()

    def clear(self) -> None:
        self._conn.execute("DELETE FROM pdf_cache")
        self._conn.commit()

    def stats(self) -> dict[str, int]:
        row = self._conn.execute(
            "SELECT COUNT(*), COALESCE(SUM(LENGTH(content)), 0) FROM pdf_cache"
        ).fetchone()
        return {"entries": row[0], "total_chars": row[1]}

    def close(self) -> None:
        self._conn.close()
