from __future__ import annotations

from dataclasses import dataclass
from typing import Callable
from uuid import uuid4

from debate_agent.domain.models import AgentOutput, ClashPoint, ClosingOutput, CoachFeedbackMode, CoachReport, DebatePhase, DebateProfile, DebateSession, EvidenceRecord, InquiryOutput, MasterAgentPlan, OpeningBrief, OpeningFramework, TimerPlan, TurnAnalysis, TurnRecord
from debate_agent.infrastructure.llm_client import DebateLLMClient
from debate_agent.orchestration.agent_services import ClosingAgent, CoachAgent, DebateAndFreeDebateAgent, InquiryAgent, MasterOrchestratorAgent, OpeningAgent, OpeningCoachAgent, OpponentAgent, SpeechAndClosingAgent, TurnAnalyzer
from debate_agent.orchestration.oversight import MatchTimerAutomation, OversightCoordinator
from debate_agent.orchestration.session_state import SessionStateMutator
from debate_agent.retrieval.evidence_service import EvidenceService
from debate_agent.retrieval.web_search import WebSearchRetriever


@dataclass(slots=True)
class ProcessTurnResult:
    user_turn: TurnRecord
    opponent_turn: TurnRecord
    master_plan: MasterAgentPlan
    timer_plan: TimerPlan
    analysis_prompt: str
    opponent_prompt: str
    coach_prompt: str | None
    turn_analysis: TurnAnalysis
    opponent_output: AgentOutput
    coach_report: CoachReport | None
    clash_points: list[ClashPoint]
    evidence_records: list[EvidenceRecord]
    model_name: str | None = None
    research_query: str | None = None


@dataclass(slots=True)
class CoachFeedbackResult:
    coach_report: CoachReport
    coach_prompt: str | None
    model_name: str | None = None
    used_cached: bool = False


@dataclass(slots=True)
class ClosingStatementResult:
    closing_output: ClosingOutput
    master_plan: MasterAgentPlan
    timer_plan: TimerPlan
    closing_prompt: str
    evidence_records: list[EvidenceRecord]
    model_name: str | None = None
    research_query: str | None = None


@dataclass(slots=True)
class OpeningBriefResult:
    opening_brief: OpeningBrief
    master_plan: MasterAgentPlan
    timer_plan: TimerPlan
    opening_prompt: str
    evidence_records: list[EvidenceRecord]
    model_name: str | None = None
    research_query: str | None = None


@dataclass(slots=True)
class OpeningFrameworkResult:
    framework: OpeningFramework
    master_plan: MasterAgentPlan
    timer_plan: TimerPlan
    opening_prompt: str
    evidence_records: list[EvidenceRecord]
    model_name: str | None = None
    research_query: str | None = None


@dataclass(slots=True)
class InquiryStrategyResult:
    inquiry_output: InquiryOutput
    master_plan: MasterAgentPlan
    timer_plan: TimerPlan
    inquiry_prompt: str
    evidence_records: list[EvidenceRecord]
    model_name: str | None = None
    research_query: str | None = None


class TurnPipeline:
    """Application-level orchestrator for turn processing and agent invocations."""

    def __init__(self, llm_client: DebateLLMClient | None = None, enable_web_search: bool | None = None) -> None:
        self.llm_client = llm_client
        web_search_enabled = llm_client.settings.web_search_enabled if llm_client else True
        if enable_web_search is not None:
            web_search_enabled = enable_web_search
        web_search_limit = llm_client.settings.web_search_limit if llm_client else 3
        web_retriever = WebSearchRetriever(enabled=web_search_enabled)
        self.evidence_service = EvidenceService(
            web_retriever=web_retriever,
            default_limit=web_search_limit + 2,
        )
        self.state_mutator = SessionStateMutator()
        self.turn_analyzer = TurnAnalyzer(llm_client=llm_client)
        opponent_model = llm_client.settings.opponent_model if llm_client else None
        coach_model = llm_client.settings.coach_model if llm_client else None
        closing_model = llm_client.settings.closing_model if llm_client else None
        opening_model = llm_client.settings.model if llm_client else None
        self.master_agent = MasterOrchestratorAgent()
        self.opponent_agent = OpponentAgent(llm_client=llm_client, model_name=opponent_model)
        self.coach_agent = CoachAgent(llm_client=llm_client, model_name=coach_model)
        self.closing_agent = ClosingAgent(llm_client=llm_client, model_name=closing_model)
        self.opening_agent = OpeningAgent(llm_client=llm_client, model_name=opening_model)
        self.opening_coach_agent = OpeningCoachAgent(llm_client=llm_client, model_name=coach_model)
        self.inquiry_agent = InquiryAgent(llm_client=llm_client, model_name=opponent_model)
        self.debate_match_agent = DebateAndFreeDebateAgent(turn_analyzer=self.turn_analyzer, opponent_agent=self.opponent_agent)
        self.speech_match_agent = SpeechAndClosingAgent(opening_agent=self.opening_agent, closing_agent=self.closing_agent)
        self.oversight_coordinator = OversightCoordinator(
            coach_agent=self.coach_agent,
            opening_coach_agent=self.opening_coach_agent,
            timer_automation=MatchTimerAutomation(),
        )

    def _latest_preparation_evidence(self, session: DebateSession) -> list[EvidenceRecord]:
        if not session.preparation_packets:
            return []
        return session.preparation_packets[-1].evidence_records

    def _merge_upstream_evidence(self, session: DebateSession, live_records: list[EvidenceRecord]) -> list[EvidenceRecord]:
        merged: list[EvidenceRecord] = []
        seen: set[str] = set()
        for record in [*self._latest_preparation_evidence(session), *live_records]:
            dedupe_key = f"{record.evidence_id}|{record.source_ref}|{record.title}|{record.snippet}"
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            merged.append(record)
        return merged

    def _retrieve_opening_evidence(self, session: DebateSession) -> tuple[list[EvidenceRecord], str | None]:
        evidence_result = self.evidence_service.retrieve(
            topic=session.topic,
            latest_user_turn=session.topic,
            clash_points=session.clash_points,
            limit=3 if not session.options.web_search_enabled else None,
            enable_web_search=session.options.web_search_enabled,
        )
        return self._merge_upstream_evidence(session, evidence_result.records), evidence_result.research_query

    def _resolve_session_speaker(self, session: DebateSession, speaker_side: str | None, default_side: str = "user") -> str:
        requested_speaker = speaker_side or default_side
        return session.user_side if requested_speaker in {"user", "me", session.user_side} else session.agent_side

    def _resolve_opening_speaker(self, session: DebateSession, speaker_side: str | None) -> str:
        return self._resolve_session_speaker(session, speaker_side, default_side="user")

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

        master_plan = self.master_agent.plan_turn(session=session, user_text=user_text)
        user_turn = self.state_mutator.create_user_turn(session, user_text)
        turn_analysis, analysis_prompt = self.debate_match_agent.analyze_turn(session, profile, user_turn)
        user_turn.argument_ids = [item.argument_id for item in turn_analysis.arguments]
        target_argument_ids = user_turn.argument_ids[:2] or [f"arg-{user_turn.turn_id}"]
        clash_points = self.state_mutator.merge_clash_points(session, turn_analysis.clash_points)
        evidence_result = self.evidence_service.retrieve(
            topic=session.topic,
            latest_user_turn=user_text,
            clash_points=clash_points,
            enable_web_search=session.options.web_search_enabled,
        )
        available_evidence_records = self._merge_upstream_evidence(session, evidence_result.records)
        opponent_output, opponent_prompt, model_name = self.debate_match_agent.generate_response(
            session=session,
            profile=profile,
            user_text=user_text,
            recent_turns_summary=turn_analysis.summary,
            active_clash_points=clash_points,
            pending_response_arguments=turn_analysis.pending_response_arguments,
            target_argument_ids=target_argument_ids,
            evidence_records=available_evidence_records,
        )
        opponent_turn, opponent_arguments = self.state_mutator.create_opponent_turn(session, opponent_output, target_argument_ids)

        coach_result: CoachFeedbackResult | None = None
        oversight_result = self.oversight_coordinator.review_turn(
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
        self.state_mutator.add_timer_plan(session, oversight_result.timer_plan)
        if oversight_result.coach_result is not None:
            generated_coach = oversight_result.coach_result
            coach_result = CoachFeedbackResult(
                coach_report=generated_coach.coach_report,
                coach_prompt=generated_coach.prompt,
                model_name=generated_coach.model_name,
                used_cached=False,
            )

        self.state_mutator.apply_turn_result(
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
        evidence_result = self.evidence_service.retrieve(
            topic=session.topic,
            latest_user_turn=latest_turn_text,
            clash_points=session.clash_points,
            limit=3 if not session.options.web_search_enabled else None,
            enable_web_search=session.options.web_search_enabled,
        )
        available_evidence_records = self._merge_upstream_evidence(session, evidence_result.records)
        speaker = self._resolve_session_speaker(session, speaker_side, default_side="opponent")
        master_plan = self.master_agent.plan_inquiry(session=session, inquiry_focus=inquiry_focus, speaker_side=speaker)
        timer_plan = self.oversight_coordinator.build_timer_plan(
            session=session,
            speaker_side=speaker,
            phase=session.current_phase,
            note="该计时规划用于组织当前质询阶段的推进节奏。",
        )
        result = self.inquiry_agent.generate(
            session=session,
            profile=profile,
            active_clash_points=session.clash_points,
            evidence_records=available_evidence_records,
            speaker_side=speaker,
            inquiry_focus=inquiry_focus,
            max_questions=max_questions,
        )
        self.state_mutator.add_timer_plan(session, timer_plan)
        self.state_mutator.add_inquiry_output(session, result.inquiry_output)
        return InquiryStrategyResult(
            inquiry_output=result.inquiry_output,
            master_plan=master_plan,
            timer_plan=timer_plan,
            inquiry_prompt=result.prompt,
            evidence_records=available_evidence_records,
            model_name=result.model_name,
            research_query=evidence_result.research_query,
        )

    def generate_coach_feedback(self, session: DebateSession, profile: DebateProfile) -> CoachFeedbackResult | None:
        latest_user_turn, latest_opponent_turn = self.state_mutator.latest_exchange_turns(session)
        if latest_user_turn is None or latest_opponent_turn is None:
            return None

        related_turn_ids = self.state_mutator.latest_exchange_turn_ids(session)
        if session.coach_reports and session.coach_reports[-1].related_turn_ids == related_turn_ids:
            return CoachFeedbackResult(
                coach_report=session.coach_reports[-1],
                coach_prompt=None,
                model_name=None,
                used_cached=True,
            )

        evidence_result = self.evidence_service.retrieve(
            topic=session.topic,
            latest_user_turn=latest_user_turn.raw_text,
            clash_points=session.clash_points,
            limit=2 if not session.options.web_search_enabled else None,
            enable_web_search=session.options.web_search_enabled,
        )
        available_evidence_records = self._merge_upstream_evidence(session, evidence_result.records)
        oversight_result = self.oversight_coordinator.review_turn(
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
        self.state_mutator.add_timer_plan(session, oversight_result.timer_plan)
        assert oversight_result.coach_result is not None
        self.state_mutator.upsert_coach_report(session, oversight_result.coach_result.coach_report)
        return CoachFeedbackResult(
            coach_report=oversight_result.coach_result.coach_report,
            coach_prompt=oversight_result.coach_result.prompt,
            model_name=oversight_result.coach_result.model_name,
            used_cached=oversight_result.coach_result.used_cached,
        )

    def generate_closing_statement(
        self,
        session: DebateSession,
        profile: DebateProfile,
        speaker_side: str | None = None,
        closing_focus: str = "总结本方最强赢点，并把对方尚未完成的证明缺口定格为判负理由。",
    ) -> ClosingStatementResult | None:
        latest_turn_text = session.turns[-1].raw_text if session.turns else ""
        evidence_result = self.evidence_service.retrieve(
            topic=session.topic,
            latest_user_turn=latest_turn_text,
            clash_points=session.clash_points,
            limit=2 if not session.options.web_search_enabled else None,
            enable_web_search=session.options.web_search_enabled,
        )
        available_evidence_records = self._merge_upstream_evidence(session, evidence_result.records)
        requested_speaker = speaker_side or session.options.default_closing_side
        speaker = session.user_side if requested_speaker in {"user", "me", session.user_side} else session.agent_side
        default_focus = closing_focus
        if not session.turns:
            default_focus = (
                f"在没有历史交锋的情况下，先为 {speaker} 生成一版可直接使用的立场陈词。"
                f"要求优先建立判断标准、给出 2 到 3 个核心赢点，并自然整合检索资料。"
            )
        master_plan = self.master_agent.plan_closing(session=session, closing_focus=default_focus, speaker_side=speaker)
        timer_plan = self.oversight_coordinator.build_timer_plan(
            session=session,
            speaker_side=speaker,
            phase=DebatePhase.CLOSING,
            note="该计时规划服务于陈词 and 结辩 agent 的输出组织。",
        )
        result = self.speech_match_agent.generate_closing(
            session=session,
            profile=profile,
            recent_turns_summary=session.context_summary,
            active_clash_points=session.clash_points,
            evidence_records=available_evidence_records,
            speaker_side=speaker,
            closing_focus=default_focus,
        )
        self.state_mutator.add_timer_plan(session, timer_plan)
        self.state_mutator.add_closing_output(session, result.closing_output)
        return ClosingStatementResult(
            closing_output=result.closing_output,
            master_plan=master_plan,
            timer_plan=timer_plan,
            closing_prompt=result.prompt,
            evidence_records=available_evidence_records,
            model_name=result.model_name,
            research_query=evidence_result.research_query,
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
        evidence_records, research_query = self._retrieve_opening_evidence(session)
        if progress_callback is not None:
            progress_callback(
                {
                    "event": "research_ready",
                    "message": "检索资料已完成，正在组织框架稿。",
                    "research_query": research_query,
                    "evidence_count": len(evidence_records),
                }
            )
        speaker = self._resolve_opening_speaker(session, speaker_side)
        master_plan = self.master_agent.plan_opening(session=session, brief_focus=brief_focus, speaker_side=speaker)
        timer_plan = self.oversight_coordinator.build_timer_plan(
            session=session,
            speaker_side=speaker,
            phase=DebatePhase.OPENING,
            note=f"目标成稿时长约 {target_duration_minutes} 分钟。",
        )
        framework_result = self.speech_match_agent.generate_opening_framework(
            session=session,
            profile=profile,
            evidence_records=evidence_records,
            speaker_side=speaker,
            brief_focus=brief_focus,
            progress_callback=progress_callback,
        )
        self.state_mutator.set_opening_framework(session, framework_result.framework)
        opening_result = self.speech_match_agent.generate_opening_from_framework(
            session=session,
            profile=profile,
            speaker_side=speaker,
            brief_focus=brief_focus,
            framework=framework_result.framework,
            target_duration_minutes=target_duration_minutes,
            progress_callback=progress_callback,
        )
        self.state_mutator.add_timer_plan(session, timer_plan)
        self.state_mutator.add_opening_brief(session, opening_result.opening_brief)
        return OpeningBriefResult(
            opening_brief=opening_result.opening_brief,
            master_plan=master_plan,
            timer_plan=timer_plan,
            opening_prompt=f"{framework_result.prompt}\n\n-----\n\n{opening_result.prompt}",
            evidence_records=evidence_records,
            model_name=opening_result.model_name or framework_result.model_name,
            research_query=research_query,
        )

    def generate_opening_framework(
        self,
        session: DebateSession,
        profile: DebateProfile,
        speaker_side: str | None = None,
        brief_focus: str = "建立本方判断标准与核心论点，只输出可打磨的框架稿。",
        progress_callback: Callable[[dict[str, object]], None] | None = None,
    ) -> OpeningFrameworkResult:
        evidence_records, research_query = self._retrieve_opening_evidence(session)
        if progress_callback is not None:
            progress_callback(
                {
                    "event": "research_ready",
                    "message": "检索资料已完成，正在组织框架稿。",
                    "research_query": research_query,
                    "evidence_count": len(evidence_records),
                }
            )
        speaker = self._resolve_opening_speaker(session, speaker_side)
        master_plan = self.master_agent.plan_opening(session=session, brief_focus=brief_focus, speaker_side=speaker)
        timer_plan = self.oversight_coordinator.build_timer_plan(
            session=session,
            speaker_side=speaker,
            phase=DebatePhase.OPENING,
            note="该计时规划用于框架稿阶段的组织，而非正式计时。",
        )
        result = self.speech_match_agent.generate_opening_framework(
            session=session,
            profile=profile,
            evidence_records=evidence_records,
            speaker_side=speaker,
            brief_focus=brief_focus,
            progress_callback=progress_callback,
        )
        self.state_mutator.add_timer_plan(session, timer_plan)
        self.state_mutator.set_opening_framework(session, result.framework)
        return OpeningFrameworkResult(
            framework=result.framework,
            master_plan=master_plan,
            timer_plan=timer_plan,
            opening_prompt=result.prompt,
            evidence_records=evidence_records,
            model_name=result.model_name,
            research_query=research_query,
        )

    def update_opening_framework(self, session: DebateSession, framework: OpeningFramework | None) -> None:
        self.state_mutator.set_opening_framework(session, framework)

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
        evidence_records, research_query = self._retrieve_opening_evidence(session)
        selected_framework = framework or self.state_mutator.current_opening_framework(session)
        if selected_framework is None:
            raise ValueError("当前会话还没有可用框架稿，请先生成或保存框架稿。")
        speaker = self._resolve_opening_speaker(session, speaker_side)
        master_plan = self.master_agent.plan_opening(session=session, brief_focus=brief_focus, speaker_side=speaker)
        timer_plan = self.oversight_coordinator.build_timer_plan(
            session=session,
            speaker_side=speaker,
            phase=DebatePhase.OPENING,
            note=f"该计时规划匹配 {target_duration_minutes} 分钟的一辩成稿扩写。",
        )
        result = self.speech_match_agent.generate_opening_from_framework(
            session=session,
            profile=profile,
            speaker_side=speaker,
            brief_focus=brief_focus,
            framework=selected_framework,
            target_duration_minutes=target_duration_minutes,
            progress_callback=progress_callback,
        )
        self.state_mutator.add_timer_plan(session, timer_plan)
        self.state_mutator.add_opening_brief(session, result.opening_brief)
        return OpeningBriefResult(
            opening_brief=result.opening_brief,
            master_plan=master_plan,
            timer_plan=timer_plan,
            opening_prompt=result.prompt,
            evidence_records=[],
            model_name=result.model_name,
            research_query=None,
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
        selected_framework = framework or self.state_mutator.current_opening_framework(session)
        if selected_framework is None:
            raise ValueError("当前会话还没有可用框架稿，请先生成或保存框架稿。")
        speaker = self._resolve_opening_speaker(session, speaker_side)
        master_plan = self.master_agent.plan_opening(session=session, brief_focus=brief_focus, speaker_side=speaker)
        timer_plan = self.oversight_coordinator.build_timer_plan(
            session=session,
            speaker_side=speaker,
            phase=DebatePhase.OPENING,
            note=f"该流式成稿计时规划匹配 {target_duration_minutes} 分钟的一辩输出。",
        )
        result = self.speech_match_agent.generate_opening_stream_from_framework(
            session=session,
            profile=profile,
            speaker_side=speaker,
            brief_focus=brief_focus,
            framework=selected_framework,
            target_duration_minutes=target_duration_minutes,
            progress_callback=progress_callback,
        )
        self.state_mutator.add_timer_plan(session, timer_plan)
        self.state_mutator.add_opening_brief(session, result.opening_brief)
        return OpeningBriefResult(
            opening_brief=result.opening_brief,
            master_plan=master_plan,
            timer_plan=timer_plan,
            opening_prompt=result.prompt,
            evidence_records=[],
            model_name=result.model_name,
            research_query=None,
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
        self.state_mutator.add_opening_brief(session, opening_brief)
        return opening_brief

    def generate_opening_brief_feedback(self, session: DebateSession, profile: DebateProfile) -> CoachFeedbackResult | None:
        opening_brief = self.state_mutator.current_opening_brief(session)
        if opening_brief is None:
            return None

        if session.coach_reports and session.coach_reports[-1].related_turn_ids == [opening_brief.brief_id]:
            return CoachFeedbackResult(
                coach_report=session.coach_reports[-1],
                coach_prompt=None,
                model_name=None,
                used_cached=True,
            )

        evidence_result = self.evidence_service.retrieve(
            topic=session.topic,
            latest_user_turn=opening_brief.spoken_text,
            clash_points=session.clash_points,
            limit=3 if not session.options.web_search_enabled else None,
            enable_web_search=session.options.web_search_enabled,
        )
        available_evidence_records = self._merge_upstream_evidence(session, evidence_result.records)
        oversight_result = self.oversight_coordinator.review_opening_brief(
            session=session,
            profile=profile,
            evidence_records=available_evidence_records,
            opening_brief=opening_brief,
        )
        self.state_mutator.add_timer_plan(session, oversight_result.timer_plan)
        self.state_mutator.upsert_coach_report(session, oversight_result.coach_report)
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
        resolved_speaker = self._resolve_session_speaker(session, speaker_side, default_side="user")
        timer_plan = self.oversight_coordinator.build_timer_plan(
            session=session,
            speaker_side=resolved_speaker,
            phase=phase,
            note=note or "该计时规划由评判与组织体系独立生成。",
        )
        self.state_mutator.add_timer_plan(session, timer_plan)
        return timer_plan