from __future__ import annotations

from debate_agent.domain.models import CoachFeedbackMode, DebateProfile, DebateSession
from debate_agent.orchestration.pipeline_models import CoachFeedbackResult, InquiryStrategyResult, ProcessTurnResult
from debate_agent.orchestration.pipeline_runtime import PipelineRuntime


class MatchEngine:
    def __init__(self, runtime: PipelineRuntime) -> None:
        self.runtime = runtime

    def process_turn(
        self,
        session: DebateSession,
        profile: DebateProfile,
        user_text: str,
        include_coach_feedback: bool | None = None,
    ) -> ProcessTurnResult:
        should_generate_coach = include_coach_feedback
        if should_generate_coach is None:
            should_generate_coach = session.options.coach_feedback_mode == CoachFeedbackMode.AUTO

        master_plan = self.runtime.master_agent.plan_turn(session=session, user_text=user_text)
        user_turn = self.runtime.state_mutator.create_user_turn(session, user_text)
        turn_analysis, analysis_prompt = self.runtime.debate_match_agent.analyze_turn(session, profile, user_turn)
        user_turn.argument_ids = [item.argument_id for item in turn_analysis.arguments]
        target_argument_ids = user_turn.argument_ids[:2] or [f"arg-{user_turn.turn_id}"]
        clash_points = self.runtime.state_mutator.merge_clash_points(session, turn_analysis.clash_points)
        evidence_result = self.runtime.evidence_service.retrieve(
            topic=session.topic,
            latest_user_turn=user_text,
            clash_points=clash_points,
            enable_web_search=session.options.web_search_enabled,
        )
        merged_evidence_records = self.runtime.merge_upstream_evidence(session, evidence_result.records)
        available_evidence_records = self.runtime.state_mutator.apply_evidence_workbench(session, merged_evidence_records, evidence_result.research_query)
        opponent_output, opponent_prompt, model_name = self.runtime.debate_match_agent.generate_response(
            session=session,
            profile=profile,
            user_text=user_text,
            recent_turns_summary=turn_analysis.summary,
            active_clash_points=clash_points,
            pending_response_arguments=turn_analysis.pending_response_arguments,
            target_argument_ids=target_argument_ids,
            evidence_records=available_evidence_records,
        )
        opponent_turn, opponent_arguments = self.runtime.state_mutator.create_opponent_turn(session, opponent_output, target_argument_ids)

        coach_result: CoachFeedbackResult | None = None
        oversight_result = self.runtime.oversight_coordinator.review_turn(
            session=session,
            profile=profile,
            recent_turns_summary=turn_analysis.summary,
            active_clash_points=clash_points,
            evidence_records=available_evidence_records,
            latest_user_turn=user_text,
            latest_opponent_turn=opponent_output.spoken_text,
            related_turn_ids=[user_turn.turn_id, opponent_turn.turn_id],
            include_coach_feedback=bool(should_generate_coach),
        )
        self.runtime.state_mutator.add_timer_plan(session, oversight_result.timer_plan)
        if oversight_result.coach_result is not None:
            generated_coach = oversight_result.coach_result
            coach_result = CoachFeedbackResult(
                coach_report=generated_coach.coach_report,
                coach_prompt=generated_coach.prompt,
                model_name=generated_coach.model_name,
                used_cached=False,
            )

        self.runtime.state_mutator.apply_turn_result(
            session=session,
            user_turn=user_turn,
            turn_analysis=turn_analysis,
            clash_points=clash_points,
            opponent_turn=opponent_turn,
            opponent_arguments=opponent_arguments,
            pending_response_argument_ids=target_argument_ids,
            pressure_score=opponent_output.pressure_score,
            coach_report=coach_result.coach_report if coach_result else None,
        )
        return ProcessTurnResult(
            user_turn=user_turn,
            opponent_turn=opponent_turn,
            master_plan=master_plan,
            timer_plan=oversight_result.timer_plan,
            analysis_prompt=analysis_prompt,
            opponent_prompt=opponent_prompt,
            coach_prompt=coach_result.coach_prompt if coach_result else None,
            turn_analysis=turn_analysis,
            opponent_output=opponent_output,
            coach_report=coach_result.coach_report if coach_result else None,
            clash_points=clash_points,
            evidence_records=available_evidence_records,
            model_name=model_name,
            research_query=evidence_result.research_query,
        )

    def generate_inquiry_strategy(
        self,
        session: DebateSession,
        profile: DebateProfile,
        speaker_side: str | None = None,
        inquiry_focus: str = "优先追打对方尚未完成的证明责任，并连续追问必要性、可行性与替代方案。",
        max_questions: int = 4,
    ) -> InquiryStrategyResult:
        latest_turn_text = session.turns[-1].raw_text if session.turns else session.topic
        evidence_result = self.runtime.evidence_service.retrieve(
            topic=session.topic,
            latest_user_turn=latest_turn_text,
            clash_points=session.clash_points,
            limit=3 if not session.options.web_search_enabled else None,
            enable_web_search=session.options.web_search_enabled,
        )
        merged_evidence_records = self.runtime.merge_upstream_evidence(session, evidence_result.records)
        available_evidence_records = self.runtime.state_mutator.apply_evidence_workbench(session, merged_evidence_records, evidence_result.research_query)
        speaker = self.runtime.resolve_session_speaker(session, speaker_side, default_side="opponent")
        master_plan = self.runtime.master_agent.plan_inquiry(session=session, inquiry_focus=inquiry_focus, speaker_side=speaker)
        timer_plan = self.runtime.oversight_coordinator.build_timer_plan(
            session=session,
            speaker_side=speaker,
            phase=session.current_phase,
            note="该计时规划用于组织当前质询阶段的推进节奏。",
        )
        result = self.runtime.inquiry_agent.generate(
            session=session,
            profile=profile,
            active_clash_points=session.clash_points,
            evidence_records=available_evidence_records,
            speaker_side=speaker,
            inquiry_focus=inquiry_focus,
            max_questions=max_questions,
        )
        self.runtime.state_mutator.add_timer_plan(session, timer_plan)
        self.runtime.state_mutator.add_inquiry_output(session, result.inquiry_output)
        return InquiryStrategyResult(
            inquiry_output=result.inquiry_output,
            master_plan=master_plan,
            timer_plan=timer_plan,
            inquiry_prompt=result.prompt,
            evidence_records=available_evidence_records,
            model_name=result.model_name,
            research_query=evidence_result.research_query,
        )