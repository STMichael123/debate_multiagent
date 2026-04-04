from __future__ import annotations

import difflib
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from uuid import uuid4

from debate_agent.domain.models import CoachFeedbackMode, CoachReport, DebatePhase, DebateProfile, DebateSession, EvidenceRecord, OpeningBrief, OpeningFramework, SessionOptions, TimerPlan
from debate_agent.orchestration.pipeline_models import ClosingStatementResult, CoachFeedbackResult, InquiryStrategyResult, OpeningBriefResult, OpeningFrameworkResult, ProcessTurnResult
from debate_agent.orchestration.preparation import PreparationCoordinator, PreparationResult
from debate_agent.orchestration.turn_pipeline import TurnPipeline
from debate_agent.storage.json_store import JSONSessionStore


@dataclass(slots=True)
class NewSessionRequest:
    topic: str
    user_side: str
    agent_side: str
    profile_id: str
    mode: str = "crossfire"
    coach_feedback_mode: CoachFeedbackMode = CoachFeedbackMode.MANUAL
    web_search_enabled: bool = True
    default_closing_side: str = "opponent"


@dataclass(slots=True)
class SessionActionResult:
    session: DebateSession
    saved_path: Path


@dataclass(slots=True)
class DeleteSessionResult:
    session_id: str
    deleted_path: Path


@dataclass(slots=True)
class TurnActionResult(SessionActionResult):
    turn_result: ProcessTurnResult


@dataclass(slots=True)
class CoachActionResult(SessionActionResult):
    coach_result: CoachFeedbackResult


@dataclass(slots=True)
class ClosingActionResult(SessionActionResult):
    closing_result: ClosingStatementResult


@dataclass(slots=True)
class InquiryActionResult(SessionActionResult):
    inquiry_result: InquiryStrategyResult


@dataclass(slots=True)
class TimerPlanActionResult(SessionActionResult):
    timer_plan: TimerPlan


@dataclass(slots=True)
class PreparationActionResult(SessionActionResult):
    preparation_result: PreparationResult


@dataclass(slots=True)
class OpeningBriefActionResult(SessionActionResult):
    opening_result: OpeningBriefResult


@dataclass(slots=True)
class OpeningFrameworkActionResult(SessionActionResult):
    framework_result: OpeningFrameworkResult


@dataclass(slots=True)
class OpeningBriefImportActionResult(SessionActionResult):
    opening_brief: OpeningBrief


class DebateApplication:
    def __init__(self, pipeline: TurnPipeline, store: JSONSessionStore, preparation_coordinator: PreparationCoordinator | None = None) -> None:
        self.pipeline = pipeline
        self.store = store
        self.preparation_coordinator = preparation_coordinator

    def create_session(self, request: NewSessionRequest) -> SessionActionResult:
        if not request.topic or not request.topic.strip():
            raise ValueError("topic 不能为空。")
        if not request.user_side or not request.user_side.strip():
            raise ValueError("user_side 不能为空。")
        if not request.agent_side or not request.agent_side.strip():
            raise ValueError("agent_side 不能为空。")
        if request.user_side.strip() == request.agent_side.strip():
            raise ValueError("user_side 和 agent_side 不能相同。")
        session = DebateSession(
            session_id=str(uuid4()),
            topic=request.topic,
            user_side=request.user_side,
            agent_side=request.agent_side,
            profile_id=request.profile_id,
            mode=request.mode,
            current_phase=DebatePhase.OPENING,
            options=SessionOptions(
                coach_feedback_mode=request.coach_feedback_mode,
                web_search_enabled=request.web_search_enabled,
                default_closing_side=request.default_closing_side,
            ),
        )
        self.pipeline.state_mutator.ensure_evidence_workbench(session)
        saved_path = self.store.save_session(session)
        return SessionActionResult(session=session, saved_path=saved_path)

    def list_session_ids(self) -> list[str]:
        return self.store.list_session_ids()

    def load_session(self, session_id: str) -> DebateSession:
        return self.store.load_session(session_id)

    def save_session(self, session: DebateSession) -> Path:
        return self.store.save_session(session)

    def delete_session(self, session_id: str) -> DeleteSessionResult:
        deleted_path = self.store.delete_session(session_id)
        return DeleteSessionResult(session_id=session_id, deleted_path=deleted_path)

    def process_user_turn(
        self,
        session: DebateSession,
        profile: DebateProfile,
        user_text: str,
        include_coach_feedback: bool | None = None,
    ) -> TurnActionResult:
        if session.current_phase == DebatePhase.OPENING:
            session.current_phase = DebatePhase.CROSSFIRE
        turn_result = self.pipeline.process_turn(
            session=session,
            profile=profile,
            user_text=user_text,
            include_coach_feedback=include_coach_feedback,
        )
        saved_path = self.store.save_session(session)
        return TurnActionResult(session=session, saved_path=saved_path, turn_result=turn_result)

    def request_coach_feedback(self, session: DebateSession, profile: DebateProfile) -> CoachActionResult | None:
        coach_result = self.pipeline.generate_coach_feedback(session, profile)
        if coach_result is None:
            return None
        saved_path = self.store.save_session(session)
        return CoachActionResult(session=session, saved_path=saved_path, coach_result=coach_result)

    def request_closing_statement(
        self,
        session: DebateSession,
        profile: DebateProfile,
        speaker_side: str | None = None,
        closing_focus: str | None = None,
    ) -> ClosingActionResult | None:
        closing_result = self.pipeline.generate_closing_statement(
            session=session,
            profile=profile,
            speaker_side=speaker_side,
            closing_focus=closing_focus or "总结本方最强赢点，并把对方尚未完成的证明缺口定格为判负理由。",
        )
        if closing_result is None:
            return None
        saved_path = self.store.save_session(session)
        return ClosingActionResult(session=session, saved_path=saved_path, closing_result=closing_result)

    def request_inquiry_strategy(
        self,
        session: DebateSession,
        profile: DebateProfile,
        speaker_side: str | None = None,
        inquiry_focus: str | None = None,
        max_questions: int = 4,
    ) -> InquiryActionResult:
        inquiry_result = self.pipeline.generate_inquiry_strategy(
            session=session,
            profile=profile,
            speaker_side=speaker_side,
            inquiry_focus=inquiry_focus or "优先追打对方尚未完成的证明责任，并连续追问必要性、可行性与替代方案。",
            max_questions=max_questions,
        )
        saved_path = self.store.save_session(session)
        return InquiryActionResult(session=session, saved_path=saved_path, inquiry_result=inquiry_result)

    def request_timer_plan(
        self,
        session: DebateSession,
        speaker_side: str | None = None,
        phase: DebatePhase | None = None,
        note: str | None = None,
    ) -> TimerPlanActionResult:
        timer_plan = self.pipeline.build_timer_plan(
            session=session,
            speaker_side=speaker_side,
            phase=phase,
            note=note,
        )
        saved_path = self.store.save_session(session)
        return TimerPlanActionResult(session=session, saved_path=saved_path, timer_plan=timer_plan)

    def prepare_session_research(
        self,
        session: DebateSession,
        profile: DebateProfile,
        preparation_goal: str | None = None,
        focus: str | None = None,
        limit: int = 6,
    ) -> PreparationActionResult:
        if self.preparation_coordinator is None:
            raise RuntimeError("当前应用未配置 preparation coordinator。")
        preparation_result = self.preparation_coordinator.prepare(
            session=session,
            profile=profile,
            preparation_goal=preparation_goal or "为备赛整理资料、学理抓手、论点种子与可能被追打的风险点。",
            focus=focus,
            limit=limit,
        )
        self.pipeline.add_preparation_packet(session, preparation_result.preparation_packet)
        saved_path = self.store.save_session(session)
        return PreparationActionResult(session=session, saved_path=saved_path, preparation_result=preparation_result)

    def generate_opening_brief(
        self,
        session: DebateSession,
        profile: DebateProfile,
        speaker_side: str | None = None,
        brief_focus: str | None = None,
        target_duration_minutes: int = 3,
        progress_callback: Callable[[dict[str, object]], None] | None = None,
    ) -> OpeningBriefActionResult:
        opening_result = self.pipeline.generate_opening_brief(
            session=session,
            profile=profile,
            speaker_side=speaker_side,
            brief_focus=brief_focus or "建立本方一辩稿骨架，让后续对辩可以围绕判断标准、核心论点和证明责任展开。",
            target_duration_minutes=target_duration_minutes,
            progress_callback=progress_callback,
        )
        saved_path = self.store.save_session(session)
        return OpeningBriefActionResult(session=session, saved_path=saved_path, opening_result=opening_result)

    def generate_opening_framework(
        self,
        session: DebateSession,
        profile: DebateProfile,
        speaker_side: str | None = None,
        brief_focus: str | None = None,
    ) -> OpeningFrameworkActionResult:
        framework_result = self.pipeline.generate_opening_framework(
            session=session,
            profile=profile,
            speaker_side=speaker_side,
            brief_focus=brief_focus or "先独立产出可打磨的框架稿，只输出判断标准、胜利路径与核心论点，不生成一辩成稿。",
        )
        saved_path = self.store.save_session(session)
        return OpeningFrameworkActionResult(session=session, saved_path=saved_path, framework_result=framework_result)

    def update_opening_framework(
        self,
        session: DebateSession,
        framework: OpeningFramework | None,
    ) -> Path:
        self.pipeline.update_opening_framework(session, framework)
        return self.store.save_session(session)

    def stream_opening_brief_from_framework(
        self,
        session: DebateSession,
        profile: DebateProfile,
        speaker_side: str | None = None,
        brief_focus: str | None = None,
        target_duration_minutes: int = 3,
        framework: OpeningFramework | None = None,
        progress_callback: Callable[[dict[str, object]], None] | None = None,
    ) -> OpeningBriefActionResult:
        opening_result = self.pipeline.generate_opening_brief_stream_from_framework(
            session=session,
            profile=profile,
            speaker_side=speaker_side,
            brief_focus=brief_focus or "严格基于当前框架稿扩写成一辩稿，不要重写框架逻辑。",
            target_duration_minutes=target_duration_minutes,
            framework=framework,
            progress_callback=progress_callback,
        )
        saved_path = self.store.save_session(session)
        return OpeningBriefActionResult(session=session, saved_path=saved_path, opening_result=opening_result)

    def inject_opening_brief(
        self,
        session: DebateSession,
        speaker_side: str,
        spoken_text: str,
        strategy_summary: str | None = None,
        outline: list[str] | None = None,
        framework: OpeningFramework | None = None,
        target_duration_minutes: int | None = None,
    ) -> OpeningBriefImportActionResult:
        opening_brief = self.pipeline.inject_opening_brief(
            session=session,
            speaker_side=speaker_side,
            spoken_text=spoken_text,
            strategy_summary=strategy_summary or "手动注入的一辩稿骨架。",
            outline=outline,
            framework=framework,
            target_duration_minutes=target_duration_minutes,
        )
        saved_path = self.store.save_session(session)
        return OpeningBriefImportActionResult(session=session, saved_path=saved_path, opening_brief=opening_brief)

    def request_opening_brief_feedback(self, session: DebateSession, profile: DebateProfile) -> CoachActionResult | None:
        coach_result = self.pipeline.generate_opening_brief_feedback(session, profile)
        if coach_result is None:
            return None
        saved_path = self.store.save_session(session)
        return CoachActionResult(session=session, saved_path=saved_path, coach_result=coach_result)

    def update_coach_feedback_mode(self, session: DebateSession, mode: CoachFeedbackMode) -> Path:
        session.options.coach_feedback_mode = mode
        return self.store.save_session(session)

    def update_session_options(
        self,
        session: DebateSession,
        coach_feedback_mode: CoachFeedbackMode | None = None,
        web_search_enabled: bool | None = None,
        default_closing_side: str | None = None,
    ) -> Path:
        if coach_feedback_mode is not None:
            session.options.coach_feedback_mode = coach_feedback_mode
        if web_search_enabled is not None:
            session.options.web_search_enabled = web_search_enabled
        if default_closing_side is not None:
            session.options.default_closing_side = default_closing_side
        return self.store.save_session(session)

    def get_evidence_workbench(self, session: DebateSession):
        return self.pipeline.state_mutator.ensure_evidence_workbench(session)

    def pin_evidence(self, session: DebateSession, evidence_id: str) -> Path:
        self.pipeline.state_mutator.pin_evidence(session, evidence_id)
        return self.store.save_session(session)

    def unpin_evidence(self, session: DebateSession, evidence_id: str) -> Path:
        self.pipeline.state_mutator.unpin_evidence(session, evidence_id)
        return self.store.save_session(session)

    def blacklist_source_type(self, session: DebateSession, source_type: str) -> Path:
        self.pipeline.state_mutator.blacklist_source_type(session, source_type)
        return self.store.save_session(session)

    def remove_blacklisted_source_type(self, session: DebateSession, source_type: str) -> Path:
        self.pipeline.state_mutator.remove_blacklisted_source_type(session, source_type)
        return self.store.save_session(session)

    def add_user_supplied_evidence(
        self,
        session: DebateSession,
        title: str,
        snippet: str,
        source_ref: str,
        user_explanation: str = "",
    ) -> Path:
        evidence_record = EvidenceRecord(
            evidence_id=f"usr-{uuid4().hex[:10]}",
            query_text=session.topic,
            source_type="user_supplied",
            source_ref=source_ref.strip() or "user://manual",
            title=title.strip(),
            snippet=snippet.strip(),
            relevance_score=1.0,
            credibility_score=0.95,
            verification_state="user_supplied",
            user_explanation=user_explanation.strip(),
        )
        self.pipeline.state_mutator.add_user_supplied_evidence(session, evidence_record)
        return self.store.save_session(session)

    def update_evidence_explanation(self, session: DebateSession, evidence_id: str, explanation: str) -> Path:
        self.pipeline.state_mutator.update_evidence_explanation(session, evidence_id, explanation)
        return self.store.save_session(session)

    def get_opening_history(self, session: DebateSession) -> dict[str, object]:
        brief_history = []
        for brief in session.opening_briefs:
            brief_history.append(
                {
                    "brief_id": brief.brief_id,
                    "created_at": brief.created_at,
                    "speaker_side": brief.speaker_side,
                    "source_mode": brief.source_mode,
                    "target_duration_minutes": brief.target_duration_minutes,
                    "word_count": len((brief.spoken_text or "").strip()),
                    "strategy_summary": brief.strategy_summary,
                    "based_on_brief_id": brief.based_on_brief_id,
                    "has_coach_report": self._find_opening_brief_coach_report(session, brief.brief_id) is not None,
                    "is_current": session.current_opening_brief_id == brief.brief_id,
                }
            )

        framework_history = []
        for version in session.opening_framework_versions:
            framework_history.append(
                {
                    "version_id": version.version_id,
                    "created_at": version.created_at,
                    "source_mode": version.source_mode,
                    "label": version.label,
                    "judge_standard": version.framework.judge_standard,
                    "framework_summary": version.framework.framework_summary,
                    "argument_count": len(version.framework.argument_cards),
                    "is_current": session.current_opening_framework_version_id == version.version_id,
                }
            )

        return {
            "current_opening_brief_id": session.current_opening_brief_id,
            "current_opening_framework_version_id": session.current_opening_framework_version_id,
            "briefs": brief_history,
            "frameworks": framework_history,
        }

    def get_opening_brief_diff(self, session: DebateSession, from_brief_id: str, to_brief_id: str) -> dict[str, object]:
        from_brief = self.pipeline.state_mutator.opening_brief_by_id(session, from_brief_id)
        to_brief = self.pipeline.state_mutator.opening_brief_by_id(session, to_brief_id)
        if from_brief is None or to_brief is None:
            raise ValueError("指定的一辩稿版本不存在。")

        diff_lines = list(
            difflib.unified_diff(
                from_brief.spoken_text.splitlines(),
                to_brief.spoken_text.splitlines(),
                fromfile=f"brief:{from_brief.brief_id}",
                tofile=f"brief:{to_brief.brief_id}",
                lineterm="",
            )
        )
        coach_before = self._serialize_coach_report(self._find_opening_brief_coach_report(session, from_brief.brief_id))
        coach_after = self._serialize_coach_report(self._find_opening_brief_coach_report(session, to_brief.brief_id))
        score_comparison = self._compare_score_cards(coach_before, coach_after)

        return {
            "from_brief": {
                "brief_id": from_brief.brief_id,
                "created_at": from_brief.created_at,
                "source_mode": from_brief.source_mode,
                "target_duration_minutes": from_brief.target_duration_minutes,
                "spoken_text": from_brief.spoken_text,
            },
            "to_brief": {
                "brief_id": to_brief.brief_id,
                "created_at": to_brief.created_at,
                "source_mode": to_brief.source_mode,
                "target_duration_minutes": to_brief.target_duration_minutes,
                "spoken_text": to_brief.spoken_text,
            },
            "unified_diff": "\n".join(diff_lines) or "当前两个版本没有文本差异。",
            "coach_before": coach_before,
            "coach_after": coach_after,
            "score_comparison": score_comparison,
        }

    def update_session_metadata(
        self,
        session: DebateSession,
        topic: str | None = None,
        user_side: str | None = None,
        agent_side: str | None = None,
    ) -> Path:
        if topic is not None and topic.strip():
            session.topic = topic.strip()
        if user_side is not None and user_side.strip():
            session.user_side = user_side.strip()
        if agent_side is not None and agent_side.strip():
            session.agent_side = agent_side.strip()
        return self.store.save_session(session)

    def update_session_phase(self, session: DebateSession, phase: DebatePhase) -> Path:
        session.current_phase = phase
        return self.store.save_session(session)

    def _find_opening_brief_coach_report(self, session: DebateSession, brief_id: str) -> CoachReport | None:
        for coach_report in reversed(session.coach_reports):
            if coach_report.related_turn_ids == [brief_id]:
                return coach_report
        return None

    def _serialize_coach_report(self, coach_report: CoachReport | None) -> dict[str, object] | None:
        if coach_report is None:
            return None
        return {
            "report_id": coach_report.report_id,
            "round_verdict": coach_report.round_verdict,
            "score_card": coach_report.score_card,
            "improvement_actions": coach_report.improvement_actions,
            "logical_fallacies": coach_report.logical_fallacies,
        }

    def _compare_score_cards(
        self,
        coach_before: dict[str, object] | None,
        coach_after: dict[str, object] | None,
    ) -> list[dict[str, object]]:
        before_scores = coach_before.get("score_card", {}) if coach_before else {}
        after_scores = coach_after.get("score_card", {}) if coach_after else {}
        keys = sorted({*before_scores.keys(), *after_scores.keys()})
        return [
            {
                "metric": key,
                "before": before_scores.get(key),
                "after": after_scores.get(key),
                "delta": (after_scores.get(key) or 0) - (before_scores.get(key) or 0),
            }
            for key in keys
        ]