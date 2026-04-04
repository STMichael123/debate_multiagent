from __future__ import annotations

import json
from pathlib import Path

from debate_agent.domain.models import DebatePhase, DebateSession
from debate_agent.storage.json_store import JSONSessionStore


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


class TestJSONSessionStoreAtomicWrite:
    def test_save_creates_file(self, tmp_path: Path):
        store = JSONSessionStore(session_dir=tmp_path)
        session = _make_session()
        saved_path = store.save_session(session)
        assert saved_path.exists()
        data = json.loads(saved_path.read_text(encoding="utf-8"))
        assert data["session_id"] == "test-session"

    def test_save_is_atomic(self, tmp_path: Path):
        store = JSONSessionStore(session_dir=tmp_path)
        session = _make_session()
        store.save_session(session)
        json_files = list(tmp_path.glob("*.json"))
        tmp_files = list(tmp_path.glob("*.tmp"))
        assert len(json_files) == 1
        assert len(tmp_files) == 0

    def test_overwrite_preserves_data(self, tmp_path: Path):
        store = JSONSessionStore(session_dir=tmp_path)
        session = _make_session(topic="original")
        store.save_session(session)
        session.topic = "updated"
        store.save_session(session)
        loaded = store.load_session("test-session")
        assert loaded.topic == "updated"

    def test_load_nonexistent_raises(self, tmp_path: Path):
        store = JSONSessionStore(session_dir=tmp_path)
        try:
            store.load_session("nonexistent")
            assert False, "Should have raised FileNotFoundError"
        except FileNotFoundError:
            pass


class TestJSONSessionStoreBackup:
    def test_save_creates_backup(self, tmp_path: Path):
        store = JSONSessionStore(session_dir=tmp_path)
        session = _make_session()
        store.save_session(session)
        session.topic = "updated"
        store.save_session(session)
        backup_dir = tmp_path / ".backup"
        assert backup_dir.exists()
        backups = list(backup_dir.glob("test-session_*.json"))
        assert len(backups) == 1
        backup_data = json.loads(backups[0].read_text(encoding="utf-8"))
        assert backup_data["topic"] == "test topic"

    def test_max_backups_enforced(self, tmp_path: Path):
        store = JSONSessionStore(session_dir=tmp_path)
        session = _make_session()
        for i in range(8):
            session.topic = f"version-{i}"
            store.save_session(session)
        backup_dir = tmp_path / ".backup"
        backups = list(backup_dir.glob("test-session_*.json"))
        assert len(backups) <= 5

    def test_no_backup_on_first_save(self, tmp_path: Path):
        store = JSONSessionStore(session_dir=tmp_path)
        session = _make_session()
        store.save_session(session)
        backup_dir = tmp_path / ".backup"
        backups = list(backup_dir.glob("*.json"))
        assert len(backups) == 0


class TestJSONSessionStoreRoundTrip:
    def test_full_session_roundtrip(self, tmp_path: Path):
        store = JSONSessionStore(session_dir=tmp_path)
        session = _make_session()
        session.context_summary = "some context"
        session.pressure_trend = [5, 7, 3]
        store.save_session(session)
        loaded = store.load_session("test-session")
        assert loaded.session_id == session.session_id
        assert loaded.topic == session.topic
        assert loaded.context_summary == session.context_summary
        assert loaded.pressure_trend == session.pressure_trend

    def test_list_session_ids(self, tmp_path: Path):
        store = JSONSessionStore(session_dir=tmp_path)
        for i in range(3):
            session = _make_session(session_id=f"session-{i}")
            store.save_session(session)
        ids = store.list_session_ids()
        assert len(ids) == 3

    def test_delete_session(self, tmp_path: Path):
        store = JSONSessionStore(session_dir=tmp_path)
        session = _make_session()
        store.save_session(session)
        deleted_path = store.delete_session("test-session")
        assert not deleted_path.exists()
