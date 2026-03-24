from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from uuid import uuid4

from debate_agent.domain.models import CoachFeedbackMode, DebatePhase, DebateProfile, DebateSession, OpeningBrief, OpeningFramework, SessionOptions
from debate_agent.orchestration.turn_pipeline import ClosingStatementResult, CoachFeedbackResult, OpeningBriefResult, OpeningFrameworkResult, ProcessTurnResult, TurnPipeline
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
class OpeningBriefActionResult(SessionActionResult):
    opening_result: OpeningBriefResult


@dataclass(slots=True)
class OpeningFrameworkActionResult(SessionActionResult):
    framework_result: OpeningFrameworkResult


@dataclass(slots=True)
class OpeningBriefImportActionResult(SessionActionResult):
    opening_brief: OpeningBrief


class DebateApplication:
    def __init__(self, pipeline: TurnPipeline, store: JSONSessionStore) -> None:
        self.pipeline = pipeline
        self.store = store

    def create_session(self, request: NewSessionRequest) -> SessionActionResult:
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