"""SQLite-backed deduplication store for cold-email runs.

Prevents drafting the same person twice across consecutive runs.
The DB file defaults to ``~/.cold_email_skill/runs.db`` and is
created automatically on first use.
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

_DEFAULT_DB = os.path.join(Path.home(), ".cold_email_skill", "runs.db")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS drafted_leads (
    email       TEXT    NOT NULL,
    specter_id  TEXT    NOT NULL,
    drafted_at  TEXT    NOT NULL,
    PRIMARY KEY (email)
);
"""


class DedupStore:
    """Tracks which emails have already had drafts created."""

    def __init__(self, db_path: str = _DEFAULT_DB) -> None:
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._conn.execute(_SCHEMA)
        self._conn.commit()

    def already_drafted(self, email: str) -> bool:
        """Return True if a draft was already created for this email."""
        row = self._conn.execute(
            "SELECT 1 FROM drafted_leads WHERE email = ?", (email,)
        ).fetchone()
        return row is not None

    def record_draft(self, email: str, specter_id: str) -> None:
        """Record that a draft was created for this email."""
        now = datetime.now(tz=timezone.utc).isoformat()
        self._conn.execute(
            "INSERT OR IGNORE INTO drafted_leads (email, specter_id, drafted_at) VALUES (?, ?, ?)",
            (email, specter_id, now),
        )
        self._conn.commit()

    def clear(self) -> None:
        """Remove all records (useful for testing or resetting)."""
        self._conn.execute("DELETE FROM drafted_leads")
        self._conn.commit()

    def count(self) -> int:
        """Return the number of tracked emails."""
        row = self._conn.execute("SELECT COUNT(*) FROM drafted_leads").fetchone()
        return row[0] if row else 0

    def close(self) -> None:
        self._conn.close()
