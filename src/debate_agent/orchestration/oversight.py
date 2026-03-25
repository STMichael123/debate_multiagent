from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from debate_agent.domain.models import ClashPoint, CoachReport, DebatePhase, DebateProfile, DebateSession, EvidenceRecord, OpeningBrief, TimerPlan
from debate_agent.orchestration.agent_services import CoachAgent, CoachGenerationResult, OpeningCoachAgent


@dataclass(slots=True)
class TurnOversightResult:
    coach_result: CoachGenerationResult | None
    timer_plan: TimerPlan


@dataclass(slots=True)
class OpeningOversightResult:
    coach_report: CoachReport
    coach_prompt: str | None
    timer_plan: TimerPlan
    model_name: str | None = None
    used_cached: bool = False


class MatchTimerAutomation:
    DEFAULT_PHASE_SECONDS = {
        DebatePhase.OPENING: 240,
        DebatePhase.CROSSFIRE: 180,
        DebatePhase.FREE_DEBATE: 240,
        DebatePhase.CLOSING: 210,
        DebatePhase.REVIEW: 120,
    }

    def build_plan(
        self,
        session: DebateSession,
        speaker_side: str,
        phase: DebatePhase | None = None,
        note: str | None = None,
    ) -> TimerPlan:
        current_phase = phase or session.current_phase
        allocated_seconds = self.DEFAULT_PHASE_SECONDS.get(current_phase, 180)
        warning_threshold_seconds = max(15, allocated_seconds // 4)
        notes = [
            f"当前阶段推荐总时长 {allocated_seconds} 秒。",
            f"剩余 {warning_threshold_seconds} 秒时应提示收束。",
        ]
        if note:
            notes.append(note)
        return TimerPlan(
            timer_id=str(uuid4()),
            session_id=session.session_id,
            phase=current_phase,
            speaker_side=speaker_side,
            allocated_seconds=allocated_seconds,
            warning_threshold_seconds=warning_threshold_seconds,
            notes=notes,
        )


class OversightCoordinator:
    def __init__(
        self,
        coach_agent: CoachAgent,
        opening_coach_agent: OpeningCoachAgent,
        timer_automation: MatchTimerAutomation | None = None,
    ) -> None:
        self.coach_agent = coach_agent
        self.opening_coach_agent = opening_coach_agent
        self.timer_automation = timer_automation or MatchTimerAutomation()

    def review_turn(
        self,
        session: DebateSession,
        profile: DebateProfile,
        recent_turns_summary: str,
        active_clash_points: list[ClashPoint],
        evidence_records: list[EvidenceRecord],
        latest_user_turn: str,
        latest_opponent_turn: str,
        related_turn_ids: list[str],
        include_coach_feedback: bool,
    ) -> TurnOversightResult:
        timer_plan = self.timer_automation.build_plan(
            session=session,
            speaker_side=session.user_side,
            note="该计时规划由自动化组件生成，用于组织当前交锋阶段。",
        )
        if not include_coach_feedback:
            return TurnOversightResult(coach_result=None, timer_plan=timer_plan)

        coach_result = self.coach_agent.generate(
            session=session,
            profile=profile,
            recent_turns_summary=recent_turns_summary,
            active_clash_points=active_clash_points,
            evidence_records=evidence_records,
            latest_user_turn=latest_user_turn,
            latest_opponent_turn=latest_opponent_turn,
            related_turn_ids=related_turn_ids,
        )
        return TurnOversightResult(coach_result=coach_result, timer_plan=timer_plan)

    def review_opening_brief(
        self,
        session: DebateSession,
        profile: DebateProfile,
        evidence_records: list[EvidenceRecord],
        opening_brief: OpeningBrief,
    ) -> OpeningOversightResult:
        timer_plan = self.timer_automation.build_plan(
            session=session,
            speaker_side=opening_brief.speaker_side,
            phase=DebatePhase.OPENING,
            note=f"当前一辩稿目标时长约 {opening_brief.target_duration_minutes} 分钟。",
        )
        result = self.opening_coach_agent.generate(
            session=session,
            profile=profile,
            evidence_records=evidence_records,
            opening_brief=opening_brief,
        )
        return OpeningOversightResult(
            coach_report=result.coach_report,
            coach_prompt=result.prompt,
            timer_plan=timer_plan,
            model_name=result.model_name,
            used_cached=result.used_cached,
        )

    def build_timer_plan(
        self,
        session: DebateSession,
        speaker_side: str,
        phase: DebatePhase | None = None,
        note: str | None = None,
    ) -> TimerPlan:
        return self.timer_automation.build_plan(session=session, speaker_side=speaker_side, phase=phase, note=note)