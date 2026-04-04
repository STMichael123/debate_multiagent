from __future__ import annotations

from typing import Callable

from debate_agent.domain.models import DebatePhase, DebateProfile, DebateSession, OpeningFramework
from debate_agent.orchestration.pipeline_models import ClosingStatementResult, OpeningBriefResult, OpeningFrameworkResult
from debate_agent.orchestration.pipeline_runtime import PipelineRuntime


class SpeechEngine:
    def __init__(self, runtime: PipelineRuntime) -> None:
        self.runtime = runtime

    def generate_closing_statement(
        self,
        session: DebateSession,
        profile: DebateProfile,
        speaker_side: str | None = None,
        closing_focus: str = "总结本方最强赢点，并把对方尚未完成的证明缺口定格为判负理由。",
    ) -> ClosingStatementResult | None:
        latest_turn_text = session.turns[-1].raw_text if session.turns else ""
        evidence_result = self.runtime.evidence_service.retrieve(
            topic=session.topic,
            latest_user_turn=latest_turn_text,
            clash_points=session.clash_points,
            limit=2 if not session.options.web_search_enabled else None,
            enable_web_search=session.options.web_search_enabled,
        )
        available_evidence_records = self.runtime.merge_upstream_evidence(session, evidence_result.records)
        requested_speaker = speaker_side or session.options.default_closing_side
        speaker = session.user_side if requested_speaker in {"user", "me", session.user_side} else session.agent_side
        default_focus = closing_focus
        if not session.turns:
            default_focus = (
                f"在没有历史交锋的情况下，先为 {speaker} 生成一版可直接使用的立场陈词。"
                f"要求优先建立判断标准、给出 2 到 3 个核心赢点，并自然整合检索资料。"
            )
        master_plan = self.runtime.master_agent.plan_closing(session=session, closing_focus=default_focus, speaker_side=speaker)
        timer_plan = self.runtime.oversight_coordinator.build_timer_plan(
            session=session,
            speaker_side=speaker,
            phase=DebatePhase.CLOSING,
            note="该计时规划服务于陈词 and 结辩 agent 的输出组织。",
        )
        result = self.runtime.speech_match_agent.generate_closing(
            session=session,
            profile=profile,
            recent_turns_summary=session.context_summary,
            active_clash_points=session.clash_points,
            evidence_records=available_evidence_records,
            speaker_side=speaker,
            closing_focus=default_focus,
        )
        self.runtime.state_mutator.add_timer_plan(session, timer_plan)
        self.runtime.state_mutator.add_closing_output(session, result.closing_output)
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
        evidence_records, research_query = self.runtime.retrieve_opening_evidence(session)
        if progress_callback is not None:
            progress_callback(
                {
                    "event": "research_ready",
                    "message": "检索资料已完成，正在组织框架稿。",
                    "research_query": research_query,
                    "evidence_count": len(evidence_records),
                }
            )
        speaker = self.runtime.resolve_opening_speaker(session, speaker_side)
        master_plan = self.runtime.master_agent.plan_opening(session=session, brief_focus=brief_focus, speaker_side=speaker)
        timer_plan = self.runtime.oversight_coordinator.build_timer_plan(
            session=session,
            speaker_side=speaker,
            phase=DebatePhase.OPENING,
            note=f"目标成稿时长约 {target_duration_minutes} 分钟。",
        )
        framework_result = self.runtime.speech_match_agent.generate_opening_framework(
            session=session,
            profile=profile,
            evidence_records=evidence_records,
            speaker_side=speaker,
            brief_focus=brief_focus,
            progress_callback=progress_callback,
        )
        self.runtime.state_mutator.set_opening_framework(session, framework_result.framework)
        opening_result = self.runtime.speech_match_agent.generate_opening_from_framework(
            session=session,
            profile=profile,
            speaker_side=speaker,
            brief_focus=brief_focus,
            framework=framework_result.framework,
            target_duration_minutes=target_duration_minutes,
            progress_callback=progress_callback,
        )
        self.runtime.state_mutator.add_timer_plan(session, timer_plan)
        self.runtime.state_mutator.add_opening_brief(session, opening_result.opening_brief)
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
        evidence_records, research_query = self.runtime.retrieve_opening_evidence(session)
        if progress_callback is not None:
            progress_callback(
                {
                    "event": "research_ready",
                    "message": "检索资料已完成，正在组织框架稿。",
                    "research_query": research_query,
                    "evidence_count": len(evidence_records),
                }
            )
        speaker = self.runtime.resolve_opening_speaker(session, speaker_side)
        master_plan = self.runtime.master_agent.plan_opening(session=session, brief_focus=brief_focus, speaker_side=speaker)
        timer_plan = self.runtime.oversight_coordinator.build_timer_plan(
            session=session,
            speaker_side=speaker,
            phase=DebatePhase.OPENING,
            note="该计时规划用于框架稿阶段的组织，而非正式计时。",
        )
        result = self.runtime.speech_match_agent.generate_opening_framework(
            session=session,
            profile=profile,
            evidence_records=evidence_records,
            speaker_side=speaker,
            brief_focus=brief_focus,
            progress_callback=progress_callback,
        )
        self.runtime.state_mutator.add_timer_plan(session, timer_plan)
        self.runtime.state_mutator.set_opening_framework(session, result.framework, source_mode="generated", label="系统生成")
        return OpeningFrameworkResult(
            framework=result.framework,
            master_plan=master_plan,
            timer_plan=timer_plan,
            opening_prompt=result.prompt,
            evidence_records=evidence_records,
            model_name=result.model_name,
            research_query=research_query,
        )

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
        evidence_records, research_query = self.runtime.retrieve_opening_evidence(session)
        selected_framework = framework or self.runtime.state_mutator.current_opening_framework(session)
        if selected_framework is None:
            raise ValueError("当前会话还没有可用框架稿，请先生成或保存框架稿。")
        speaker = self.runtime.resolve_opening_speaker(session, speaker_side)
        master_plan = self.runtime.master_agent.plan_opening(session=session, brief_focus=brief_focus, speaker_side=speaker)
        timer_plan = self.runtime.oversight_coordinator.build_timer_plan(
            session=session,
            speaker_side=speaker,
            phase=DebatePhase.OPENING,
            note=f"该计时规划匹配 {target_duration_minutes} 分钟的一辩成稿扩写。",
        )
        result = self.runtime.speech_match_agent.generate_opening_from_framework(
            session=session,
            profile=profile,
            speaker_side=speaker,
            brief_focus=brief_focus,
            framework=selected_framework,
            target_duration_minutes=target_duration_minutes,
            progress_callback=progress_callback,
        )
        self.runtime.state_mutator.add_timer_plan(session, timer_plan)
        self.runtime.state_mutator.add_opening_brief(session, result.opening_brief)
        return OpeningBriefResult(
            opening_brief=result.opening_brief,
            master_plan=master_plan,
            timer_plan=timer_plan,
            opening_prompt=result.prompt,
            evidence_records=evidence_records,
            model_name=result.model_name,
            research_query=research_query,
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
        selected_framework = framework or self.runtime.state_mutator.current_opening_framework(session)
        if selected_framework is None:
            raise ValueError("当前会话还没有可用框架稿，请先生成或保存框架稿。")
        speaker = self.runtime.resolve_opening_speaker(session, speaker_side)
        master_plan = self.runtime.master_agent.plan_opening(session=session, brief_focus=brief_focus, speaker_side=speaker)
        timer_plan = self.runtime.oversight_coordinator.build_timer_plan(
            session=session,
            speaker_side=speaker,
            phase=DebatePhase.OPENING,
            note=f"该流式成稿计时规划匹配 {target_duration_minutes} 分钟的一辩输出。",
        )
        result = self.runtime.speech_match_agent.generate_opening_stream_from_framework(
            session=session,
            profile=profile,
            speaker_side=speaker,
            brief_focus=brief_focus,
            framework=selected_framework,
            target_duration_minutes=target_duration_minutes,
            progress_callback=progress_callback,
        )
        self.runtime.state_mutator.add_timer_plan(session, timer_plan)
        self.runtime.state_mutator.add_opening_brief(session, result.opening_brief)
        return OpeningBriefResult(
            opening_brief=result.opening_brief,
            master_plan=master_plan,
            timer_plan=timer_plan,
            opening_prompt=result.prompt,
            evidence_records=[],
            model_name=result.model_name,
            research_query=None,
        )