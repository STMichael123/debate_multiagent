from __future__ import annotations

import json
from pathlib import Path

import pytest

from debate_agent.domain.models import DebatePhase, DebateSession
from debate_agent.storage.sqlite_store import SQLiteSessionStore


def _make_session(session_id: str = "test-session", topic: str = "test topic") -> DebateSession:
    return DebateSession(
        session_id=session_id,
        topic=topic,
        user_side="正方",
        agent_side="反方",
        profile_id="default",
        mode="crossfire",
        current_phase=DebatePhase.OPENING,
    )


class TestSQLiteSessionStore:
    def test_save_and_load(self, tmp_path: Path):
        store = SQLiteSessionStore(db_path=tmp_path / "test.db")
        session = _make_session()
        store.save_session(session)
        loaded = store.load_session("test-session")
        assert loaded.session_id == "test-session"
        assert loaded.topic == "test topic"
        store.close()

    def test_list_session_ids(self, tmp_path: Path):
        store = SQLiteSessionStore(db_path=tmp_path / "test.db")
        for i in range(3):
            store.save_session(_make_session(session_id=f"s-{i}"))
        ids = store.list_session_ids()
        assert len(ids) == 3
        store.close()

    def test_delete_session(self, tmp_path: Path):
        store = SQLiteSessionStore(db_path=tmp_path / "test.db")
        store.save_session(_make_session())
        store.delete_session("test-session")
        with pytest.raises(FileNotFoundError):
            store.load_session("test-session")
        store.close()

    def test_overwrite_session(self, tmp_path: Path):
        store = SQLiteSessionStore(db_path=tmp_path / "test.db")
        session = _make_session(topic="original")
        store.save_session(session)
        session.topic = "updated"
        store.save_session(session)
        loaded = store.load_session("test-session")
        assert loaded.topic == "updated"
        store.close()

    def test_load_nonexistent_raises(self, tmp_path: Path):
        store = SQLiteSessionStore(db_path=tmp_path / "test.db")
        with pytest.raises(FileNotFoundError):
            store.load_session("nonexistent")
        store.close()

    def test_wal_mode_enabled(self, tmp_path: Path):
        store = SQLiteSessionStore(db_path=tmp_path / "test.db")
        conn = store._get_conn()
        row = conn.execute("PRAGMA journal_mode").fetchone()
        assert row[0] in ("wal",)
        store.close()
