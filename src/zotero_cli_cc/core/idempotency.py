"""SQLite-backed idempotency cache for mutating commands.

An agent that retries a `zot add --idempotency-key K ...` call with the same
key within TTL gets back the original envelope instead of duplicating the
mutation upstream. Safe retries are the whole point of idempotency keys:
agents don't have to know whether the previous attempt actually committed.

The cache is keyed by (scope, key). Scope is command-specific
("add:doi:10.1/x", "update:ABC123", etc.) so two commands using the same
user-supplied key don't collide.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path

TTL_SECONDS = 24 * 60 * 60


def _db_path() -> Path:
    override = os.environ.get("ZOT_CACHE_DIR")
    base = Path(override) if override else Path.home() / ".cache" / "zotero-cli-cc"
    base.mkdir(parents=True, exist_ok=True)
    return base / "idempotency.db"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path())
    conn.execute(
        "CREATE TABLE IF NOT EXISTS cache ("
        "scope TEXT NOT NULL, key TEXT NOT NULL, value TEXT NOT NULL, "
        "created_at INTEGER NOT NULL, PRIMARY KEY (scope, key))"
    )
    return conn


def get_cached(scope: str, key: str) -> dict | None:
    if not key:
        return None
    now = int(time.time())
    with _connect() as conn:
        row = conn.execute(
            "SELECT value, created_at FROM cache WHERE scope=? AND key=?",
            (scope, key),
        ).fetchone()
    if row is None:
        return None
    value_json, created_at = row
    if now - created_at > TTL_SECONDS:
        return None
    try:
        return json.loads(value_json)
    except json.JSONDecodeError:
        return None


def store_cached(scope: str, key: str, envelope: dict) -> None:
    if not key:
        return
    now = int(time.time())
    with _connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO cache (scope, key, value, created_at) VALUES (?, ?, ?, ?)",
            (scope, key, json.dumps(envelope), now),
        )


def clear() -> None:
    """Clear the entire cache. Exposed for tests."""
    with _connect() as conn:
        conn.execute("DELETE FROM cache")
