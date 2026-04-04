from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from pathlib import Path
from typing import Generator

from debate_agent.domain.models import DebateSession
from debate_agent.storage.json_store import JSONSessionStore

_SCHEMA_VERSION = 1

_CREATE_TABLES = """
CREATE TABLE IF NOT EXISTS session_meta (
    session_id TEXT PRIMARY KEY,
    topic TEXT NOT NULL,
    user_side TEXT NOT NULL,
    agent_side TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS session_data (
    session_id TEXT PRIMARY KEY REFERENCES session_meta(session_id) ON DELETE CASCADE,
    payload TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY
);

INSERT OR IGNORE INTO schema_version (version) VALUES (?);
"""


class SQLiteSessionStore:
    """SQLite-backed session store with JSON serialization.

    Provides the same interface as JSONSessionStore but with:
    - Concurrent access safety via WAL mode
    - Efficient session listing without reading full payloads
    - Atomic transactions
    """

    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or self._default_db_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def _init_db(self) -> None:
        conn = self._get_conn()
        conn.executescript(_CREATE_TABLES)
        conn.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (?)", (_SCHEMA_VERSION,))
        conn.commit()

    def save_session(self, session: DebateSession) -> Path:
        payload = json.dumps(asdict(session), ensure_ascii=False)
        conn = self._get_conn()
        with conn:
            conn.execute(
                """INSERT INTO session_meta (session_id, topic, user_side, agent_side, updated_at)
                   VALUES (?, ?, ?, ?, datetime('now'))
                   ON CONFLICT(session_id) DO UPDATE SET
                       topic=excluded.topic, user_side=excluded.user_side,
                       agent_side=excluded.agent_side, updated_at=excluded.updated_at""",
                (session.session_id, session.topic, session.user_side, session.agent_side),
            )
            conn.execute(
                """INSERT INTO session_data (session_id, payload)
                   VALUES (?, ?)
                   ON CONFLICT(session_id) DO UPDATE SET payload=excluded.payload""",
                (session.session_id, payload),
            )
        return self.db_path

    def load_session(self, session_id: str) -> DebateSession:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT payload FROM session_data WHERE session_id = ?", (session_id,)
        ).fetchone()
        if row is None:
            raise FileNotFoundError(f"Session not found: {session_id}")
        # Reuse JSONSessionStore's deserialization logic
        json_store = JSONSessionStore.__new__(JSONSessionStore)
        return json_store._build_session(json.loads(row["payload"]))

    def list_session_ids(self) -> list[str]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT session_id FROM session_meta ORDER BY updated_at DESC"
        ).fetchall()
        return [row["session_id"] for row in rows]

    def delete_session(self, session_id: str) -> Path:
        conn = self._get_conn()
        with conn:
            conn.execute("DELETE FROM session_data WHERE session_id = ?", (session_id,))
            conn.execute("DELETE FROM session_meta WHERE session_id = ?", (session_id,))
        return self.db_path

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def _default_db_path(self) -> Path:
        return Path(__file__).resolve().parents[3] / "data" / "sessions.db"
