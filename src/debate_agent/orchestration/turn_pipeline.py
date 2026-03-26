from __future__ import annotations

from typing import Callable

from debate_agent.domain.models import DebatePhase, DebateProfile, DebateSession, OpeningBrief, OpeningFramework, PreparationPacket, TimerPlan
from debate_agent.infrastructure.llm_client import DebateLLMClient
from debate_agent.orchestration.match_engine import MatchEngine
from debate_agent.orchestration.pipeline_models import ClosingStatementResult, CoachFeedbackResult, InquiryStrategyResult, OpeningBriefResult, OpeningFrameworkResult, ProcessTurnResult
from debate_agent.orchestration.pipeline_runtime import PipelineRuntime
from debate_agent.orchestration.review_engine import ReviewEngine
from debate_agent.orchestration.speech_engine import SpeechEngine


class TurnPipeline:
    """Compatibility facade that preserves the public API while delegating to focused engines."""

    def __init__(self, llm_client: DebateLLMClient | None = None, enable_web_search: bool | None = None) -> None:
        self.llm_client = llm_client
        self.runtime = PipelineRuntime(llm_client=llm_client, enable_web_search=enable_web_search)
        self.evidence_service = self.runtime.evidence_service
        self.state_mutator = self.runtime.state_mutator
        self.turn_analyzer = self.runtime.turn_analyzer
        self.master_agent = self.runtime.master_agent
        self.opponent_agent = self.runtime.opponent_agent
        self.coach_agent = self.runtime.coach_agent
        self.closing_agent = self.runtime.closing_agent
        self.opening_agent = self.runtime.opening_agent
        self.opening_coach_agent = self.runtime.opening_coach_agent
        self.inquiry_agent = self.runtime.inquiry_agent
        self.debate_match_agent = self.runtime.debate_match_agent
        self.speech_match_agent = self.runtime.speech_match_agent
        self.oversight_coordinator = self.runtime.oversight_coordinator
        self.match_engine = MatchEngine(self.runtime)
        self.speech_engine = SpeechEngine(self.runtime)
        self.review_engine = ReviewEngine(self.runtime)

    def process_turn(
        self,
        session: DebateSession,
        profile: DebateProfile,
        user_text: str,
        include_coach_feedback: bool | None = None,
    ) -> ProcessTurnResult:
        return self.match_engine.process_turn(
            session=session,
            profile=profile,
            user_text=user_text,
            include_coach_feedback=include_coach_feedback,
        )

    def generate_inquiry_strategy(
        self,
        session: DebateSession,
        profile: DebateProfile,
        speaker_side: str | None = None,
        inquiry_focus: str = "优先追打对方尚未完成的证明责任，并连续追问必要性、可行性与替代方案。",
        max_questions: int = 4,
    ) -> InquiryStrategyResult:
        return self.match_engine.generate_inquiry_strategy(
            session=session,
            profile=profile,
            speaker_side=speaker_side,
            inquiry_focus=inquiry_focus,
            max_questions=max_questions,
        )

    def generate_coach_feedback(self, session: DebateSession, profile: DebateProfile) -> CoachFeedbackResult | None:
        return self.review_engine.generate_coach_feedback(session, profile)

    def generate_closing_statement(
        self,
        session: DebateSession,
        profile: DebateProfile,
        speaker_side: str | None = None,
        closing_focus: str = "总结本方最强赢点，并把对方尚未完成的证明缺口定格为判负理由。",
    ) -> ClosingStatementResult | None:
        return self.speech_engine.generate_closing_statement(
            session=session,
            profile=profile,
            speaker_side=speaker_side,
            closing_focus=closing_focus,
        )

    def generate_opening_brief(
        self,
        session: DebateSession,
        profile: DebateProfile,
        speaker_side: str | None = None,
        brief_focus: str = "建立本方一辩稿骨架，让后续对辩可以围绕判断标准、核心论点和证明责任展开。",
        target_duration_minutes: int = 3,
        progress_callback: Callable[[dict[str, object]], None] | None = None,
    ) -> OpeningBriefResult:
        return self.speech_engine.generate_opening_brief(
            session=session,
            profile=profile,
            speaker_side=speaker_side,
            brief_focus=brief_focus,
            target_duration_minutes=target_duration_minutes,
            progress_callback=progress_callback,
        )

    def generate_opening_framework(
        self,
        session: DebateSession,
        profile: DebateProfile,
        speaker_side: str | None = None,
        brief_focus: str = "建立本方判断标准与核心论点，只输出可打磨的框架稿。",
        progress_callback: Callable[[dict[str, object]], None] | None = None,
    ) -> OpeningFrameworkResult:
        return self.speech_engine.generate_opening_framework(
            session=session,
            profile=profile,
            speaker_side=speaker_side,
            brief_focus=brief_focus,
            progress_callback=progress_callback,
        )

    def update_opening_framework(self, session: DebateSession, framework: OpeningFramework | None) -> None:
        self.review_engine.update_opening_framework(session, framework)

    def generate_opening_brief_from_framework(
        self,
        session: DebateSession,
        profile: DebateProfile,
        speaker_side: str | None = None,
        brief_focus: str = "严格基于当前框架稿扩写一辩稿。",
        target_duration_minutes: int = 3,
        framework: OpeningFramework | None = None,
        progress_callback: Callable[[dict[str, object]], None] | None = None,
    ) -> OpeningBriefResult:
        return self.speech_engine.generate_opening_brief_from_framework(
            session=session,
            profile=profile,
            speaker_side=speaker_side,
            brief_focus=brief_focus,
            target_duration_minutes=target_duration_minutes,
            framework=framework,
            progress_callback=progress_callback,
        )

    def generate_opening_brief_stream_from_framework(
        self,
        session: DebateSession,
        profile: DebateProfile,
        speaker_side: str | None = None,
        brief_focus: str = "严格基于当前框架稿扩写一辩稿。",
        target_duration_minutes: int = 3,
        framework: OpeningFramework | None = None,
        progress_callback: Callable[[dict[str, object]], None] | None = None,
    ) -> OpeningBriefResult:
        return self.speech_engine.generate_opening_brief_stream_from_framework(
            session=session,
            profile=profile,
            speaker_side=speaker_side,
            brief_focus=brief_focus,
            target_duration_minutes=target_duration_minutes,
            framework=framework,
            progress_callback=progress_callback,
        )

    def inject_opening_brief(
        self,
        session: DebateSession,
        speaker_side: str,
        spoken_text: str,
        strategy_summary: str = "手动注入的一辩稿骨架。",
        outline: list[str] | None = None,
        framework: OpeningFramework | None = None,
        target_duration_minutes: int | None = None,
    ) -> OpeningBrief:
        return self.review_engine.inject_opening_brief(
            session=session,
            speaker_side=speaker_side,
            spoken_text=spoken_text,
            strategy_summary=strategy_summary,
            outline=outline,
            framework=framework,
            target_duration_minutes=target_duration_minutes,
        )

    def generate_opening_brief_feedback(self, session: DebateSession, profile: DebateProfile) -> CoachFeedbackResult | None:
        return self.review_engine.generate_opening_brief_feedback(session, profile)

    def build_timer_plan(
        self,
        session: DebateSession,
        speaker_side: str | None = None,
        phase: DebatePhase | None = None,
        note: str | None = None,
    ) -> TimerPlan:
        return self.review_engine.build_timer_plan(
            session=session,
            speaker_side=speaker_side,
            phase=phase,
            note=note,
        )

    def add_preparation_packet(self, session: DebateSession, preparation_packet: PreparationPacket) -> None:
        self.state_mutator.add_preparation_packet(session, preparation_packet)