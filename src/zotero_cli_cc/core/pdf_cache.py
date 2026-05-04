from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_CACHE_PATH = Path.home() / ".config" / "zot" / "cache" / "pdf_cache.sqlite"


class PdfCache:
    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path or DEFAULT_CACHE_PATH
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path))
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS pdf_cache ("
            "  pdf_path TEXT NOT NULL,"
            "  extractor TEXT NOT NULL DEFAULT '',"
            "  mtime REAL NOT NULL,"
            "  content TEXT NOT NULL,"
            "  extracted_at TEXT NOT NULL,"
            "  PRIMARY KEY (pdf_path, extractor)"
            ")"
        )
        self._conn.commit()

    def get(self, pdf_path: Path, extractor_name: str = "") -> str | None:
        if not pdf_path.exists():
            return None
        current_mtime = pdf_path.stat().st_mtime
        row = self._conn.execute(
            "SELECT content, mtime FROM pdf_cache WHERE pdf_path = ? AND extractor = ?",
            (str(pdf_path), extractor_name),
        ).fetchone()
        if row is None:
            return None
        if abs(row[1] - current_mtime) > 0.001:
            return None
        return str(row[0])

    def put(self, pdf_path: Path, extractor_name_or_content: str, content: str | None = None) -> None:
        if content is None:
            content = extractor_name_or_content
            extractor_name = ""
        else:
            extractor_name = extractor_name_or_content
        mtime = pdf_path.stat().st_mtime
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            "INSERT OR REPLACE INTO pdf_cache (pdf_path, extractor, mtime, content, extracted_at) VALUES (?, ?, ?, ?, ?)",
            (str(pdf_path), extractor_name, mtime, content, now),
        )
        self._conn.commit()

    def clear(self) -> None:
        self._conn.execute("DELETE FROM pdf_cache")
        self._conn.commit()

    def stats(self) -> dict[str, int]:
        row = self._conn.execute("SELECT COUNT(*), COALESCE(SUM(LENGTH(content)), 0) FROM pdf_cache").fetchone()
        return {"entries": row[0], "total_chars": row[1]}

    def close(self) -> None:
        self._conn.close()


UnifiedPdfCache = PdfCache
