from __future__ import annotations

from uuid import uuid4

from debate_agent.domain.models import DebatePhase, DebateProfile, DebateSession, OpeningBrief, OpeningFramework, TimerPlan
from debate_agent.orchestration.pipeline_models import CoachFeedbackResult
from debate_agent.orchestration.pipeline_runtime import PipelineRuntime


class ReviewEngine:
    def __init__(self, runtime: PipelineRuntime) -> None:
        self.runtime = runtime

    def generate_coach_feedback(self, session: DebateSession, profile: DebateProfile) -> CoachFeedbackResult | None:
        latest_user_turn, latest_opponent_turn = self.runtime.state_mutator.latest_exchange_turns(session)
        if latest_user_turn is None or latest_opponent_turn is None:
            return None

        related_turn_ids = self.runtime.state_mutator.latest_exchange_turn_ids(session)
        if session.coach_reports and session.coach_reports[-1].related_turn_ids == related_turn_ids:
            return CoachFeedbackResult(
                coach_report=session.coach_reports[-1],
                coach_prompt=None,
                model_name=None,
                used_cached=True,
            )

        evidence_result = self.runtime.evidence_service.retrieve(
            topic=session.topic,
            latest_user_turn=latest_user_turn.raw_text,
            clash_points=session.clash_points,
            limit=2 if not session.options.web_search_enabled else None,
            enable_web_search=session.options.web_search_enabled,
        )
        available_evidence_records = self.runtime.merge_upstream_evidence(session, evidence_result.records)
        oversight_result = self.runtime.oversight_coordinator.review_turn(
            session=session,
            profile=profile,
            recent_turns_summary=session.context_summary,
            active_clash_points=session.clash_points,
            evidence_records=available_evidence_records,
            latest_user_turn=latest_user_turn.raw_text,
            latest_opponent_turn=latest_opponent_turn.raw_text,
            related_turn_ids=related_turn_ids,
            include_coach_feedback=True,
        )
        self.runtime.state_mutator.add_timer_plan(session, oversight_result.timer_plan)
        assert oversight_result.coach_result is not None
        self.runtime.state_mutator.upsert_coach_report(session, oversight_result.coach_result.coach_report)
        return CoachFeedbackResult(
            coach_report=oversight_result.coach_result.coach_report,
            coach_prompt=oversight_result.coach_result.prompt,
            model_name=oversight_result.coach_result.model_name,
            used_cached=oversight_result.coach_result.used_cached,
        )

    def generate_opening_brief_feedback(self, session: DebateSession, profile: DebateProfile) -> CoachFeedbackResult | None:
        opening_brief = self.runtime.state_mutator.current_opening_brief(session)
        if opening_brief is None:
            return None

        if session.coach_reports and session.coach_reports[-1].related_turn_ids == [opening_brief.brief_id]:
            return CoachFeedbackResult(
                coach_report=session.coach_reports[-1],
                coach_prompt=None,
                model_name=None,
                used_cached=True,
            )

        evidence_result = self.runtime.evidence_service.retrieve(
            topic=session.topic,
            latest_user_turn=opening_brief.spoken_text,
            clash_points=session.clash_points,
            limit=3 if not session.options.web_search_enabled else None,
            enable_web_search=session.options.web_search_enabled,
        )
        available_evidence_records = self.runtime.merge_upstream_evidence(session, evidence_result.records)
        oversight_result = self.runtime.oversight_coordinator.review_opening_brief(
            session=session,
            profile=profile,
            evidence_records=available_evidence_records,
            opening_brief=opening_brief,
        )
        self.runtime.state_mutator.add_timer_plan(session, oversight_result.timer_plan)
        self.runtime.state_mutator.upsert_coach_report(session, oversight_result.coach_report)
        return CoachFeedbackResult(
            coach_report=oversight_result.coach_report,
            coach_prompt=oversight_result.coach_prompt,
            model_name=oversight_result.model_name,
            used_cached=oversight_result.used_cached,
        )

    def build_timer_plan(
        self,
        session: DebateSession,
        speaker_side: str | None = None,
        phase: DebatePhase | None = None,
        note: str | None = None,
    ) -> TimerPlan:
        resolved_speaker = self.runtime.resolve_session_speaker(session, speaker_side, default_side="user")
        timer_plan = self.runtime.oversight_coordinator.build_timer_plan(
            session=session,
            speaker_side=resolved_speaker,
            phase=phase,
            note=note or "该计时规划由评判与组织体系独立生成。",
        )
        self.runtime.state_mutator.add_timer_plan(session, timer_plan)
        return timer_plan

    def update_opening_framework(self, session: DebateSession, framework: OpeningFramework | None) -> None:
        self.runtime.state_mutator.set_opening_framework(session, framework)

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
        normalized_duration = max(1, min(target_duration_minutes or 3, 8))
        opening_brief = OpeningBrief(
            brief_id=str(uuid4()),
            session_id=session.session_id,
            speaker_side=speaker_side,
            strategy_summary=strategy_summary or (framework.framework_summary if framework else "手动注入的一辩稿骨架。"),
            outline=outline or ([card.claim[:18] + ("..." if len(card.claim) > 18 else "") for card in framework.argument_cards if card.claim] if framework else []),
            spoken_text=spoken_text,
            evidence_citations=[],
            confidence_notes=["该一辩稿由用户手动注入。"],
            source_mode="manual",
            framework=framework,
            target_duration_minutes=normalized_duration,
            target_word_count=normalized_duration * 300,
        )
        self.runtime.state_mutator.add_opening_brief(session, opening_brief)
        return opening_brief