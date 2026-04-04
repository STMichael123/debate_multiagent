from __future__ import annotations

import json
from pathlib import Path

from debate_agent.domain.models import (
    DebatePhase,
    DebateSession,
    EvidenceRecord,
    EvidenceWorkbenchState,
    OpeningArgumentCard,
    OpeningBrief,
    OpeningFramework,
    OpeningFrameworkVersion,
)
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

    def test_opening_history_and_evidence_workbench_roundtrip(self, tmp_path: Path):
        store = JSONSessionStore(session_dir=tmp_path)
        session = _make_session()
        framework = OpeningFramework(
            judge_standard="比较哪一方更能稳定提升学生 AI 基础能力并控制资源挤出。",
            framework_summary="先定标准，再比较基础能力、教育公平与执行成本。",
            argument_cards=[
                OpeningArgumentCard(
                    claim="AI 通识教育能补齐全体学生的基础识读能力。",
                    data_support="当前缺少可直接上场的硬证据。",
                    academic_support="通识教育的目标是建立跨专业的基本认知能力。",
                    scenario_support="学生面对 AI 生成内容时，若没有基础识读能力，就更容易误判信息。",
                )
            ],
        )
        session.current_opening_framework = framework
        session.opening_framework_versions.append(
            OpeningFrameworkVersion(
                version_id="framework-v1",
                session_id=session.session_id,
                framework=framework,
                created_at=1710000000.0,
                source_mode="manual",
                label="用户编辑",
            )
        )
        session.current_opening_framework_version_id = "framework-v1"
        session.opening_briefs.append(
            OpeningBrief(
                brief_id="brief-v1",
                session_id=session.session_id,
                speaker_side="正方",
                strategy_summary="先定标准，再论证 AI 通识教育的必要性与可执行性。",
                spoken_text="各位评判，本题应先比较哪一方更能补齐学生 AI 基础能力。",
                framework=framework,
                created_at=1710000100.0,
            )
        )
        session.current_opening_brief_id = "brief-v1"
        session.evidence_workbench = EvidenceWorkbenchState(
            session_id=session.session_id,
            available_evidence=[
                EvidenceRecord(
                    evidence_id="e-1",
                    query_text=session.topic,
                    source_type="user_supplied",
                    source_ref="manual://pilot-program",
                    title="地方试点课程数据",
                    snippet="试点学校已把 AI 素养纳入信息技术课程，学生参与率持续提升。",
                    verification_state="user_supplied",
                    user_explanation="用于证明课程推广已有现实基础。",
                    is_pinned=True,
                )
            ],
            pinned_evidence=[
                EvidenceRecord(
                    evidence_id="e-1",
                    query_text=session.topic,
                    source_type="user_supplied",
                    source_ref="manual://pilot-program",
                    title="地方试点课程数据",
                    snippet="试点学校已把 AI 素养纳入信息技术课程，学生参与率持续提升。",
                    verification_state="user_supplied",
                    user_explanation="用于证明课程推广已有现实基础。",
                    is_pinned=True,
                )
            ],
            user_supplied_evidence=[
                EvidenceRecord(
                    evidence_id="e-1",
                    query_text=session.topic,
                    source_type="user_supplied",
                    source_ref="manual://pilot-program",
                    title="地方试点课程数据",
                    snippet="试点学校已把 AI 素养纳入信息技术课程，学生参与率持续提升。",
                    verification_state="user_supplied",
                    user_explanation="用于证明课程推广已有现实基础。",
                    is_pinned=True,
                )
            ],
            blacklisted_source_types=["web_search"],
            last_research_query="AI 通识教育 官方试点 数据",
        )

        store.save_session(session)
        loaded = store.load_session(session.session_id)

        assert loaded.current_opening_brief_id == "brief-v1"
        assert loaded.current_opening_framework_version_id == "framework-v1"
        assert len(loaded.opening_framework_versions) == 1
        assert loaded.opening_briefs[0].created_at == 1710000100.0
        assert loaded.evidence_workbench is not None
        assert loaded.evidence_workbench.blacklisted_source_types == ["web_search"]
        assert loaded.evidence_workbench.pinned_evidence[0].is_pinned is True
        assert loaded.evidence_workbench.user_supplied_evidence[0].user_explanation == "用于证明课程推广已有现实基础。"
