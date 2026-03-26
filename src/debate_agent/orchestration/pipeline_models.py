from __future__ import annotations

from dataclasses import dataclass

from debate_agent.domain.models import AgentOutput, ClashPoint, ClosingOutput, CoachReport, EvidenceRecord, InquiryOutput, MasterAgentPlan, OpeningBrief, OpeningFramework, TimerPlan, TurnAnalysis, TurnRecord


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