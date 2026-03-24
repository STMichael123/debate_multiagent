from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class DebatePhase(str, Enum):
    OPENING = "opening"
    CROSSFIRE = "crossfire"
    FREE_DEBATE = "free_debate"
    CLOSING = "closing"
    REVIEW = "review"


class DebateType(str, Enum):
    POLICY = "policy"
    VALUE = "value"
    FACT = "fact"


class SpeakerRole(str, Enum):
    USER = "user"
    OPPONENT = "opponent"
    COACH = "coach"


class CoachFeedbackMode(str, Enum):
    MANUAL = "manual"
    AUTO = "auto"


@dataclass(slots=True)
class ArgumentUnit:
    argument_id: str
    turn_id: str
    speaker_role: SpeakerRole
    claim: str
    warrant: str = ""
    impact: str = ""
    argument_type: str = ""
    tags: list[str] = field(default_factory=list)
    strength_score: float | None = None
    status: str = "open"
    parent_argument_id: str | None = None
    attacks_argument_id: str | None = None


@dataclass(slots=True)
class ClashPoint:
    clash_point_id: str
    topic_label: str
    summary: str
    user_argument_ids: list[str] = field(default_factory=list)
    agent_argument_ids: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    current_pressure_side: str = "neutral"
    resolution_status: str = "open"
    last_updated_turn_id: str | None = None


@dataclass(slots=True)
class EvidenceRecord:
    evidence_id: str
    query_text: str
    source_type: str
    source_ref: str
    title: str
    snippet: str
    stance_hint: str = ""
    relevance_score: float | None = None
    credibility_score: float | None = None
    used_by_turn_ids: list[str] = field(default_factory=list)
    verification_state: str = "unverified"


@dataclass(slots=True)
class DebateProfile:
    profile_id: str
    debate_type: DebateType
    judge_standard: str
    burden_rules: list[str]
    preferred_attack_patterns: list[str]
    preferred_question_patterns: list[str]
    evidence_policy: list[str]
    style_constraints: list[str]
    phase_policies: dict[str, dict[str, Any]] = field(default_factory=dict)


@dataclass(slots=True)
class SessionOptions:
    coach_feedback_mode: CoachFeedbackMode = CoachFeedbackMode.MANUAL
    web_search_enabled: bool = True
    default_closing_side: str = "opponent"


@dataclass(slots=True)
class TurnRecord:
    turn_id: str
    session_id: str
    speaker_role: SpeakerRole
    phase: DebatePhase
    raw_text: str
    normalized_text: str = ""
    argument_ids: list[str] = field(default_factory=list)
    targeted_argument_ids: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    token_usage: int | None = None
    latency_ms: int | None = None


@dataclass(slots=True)
class AgentOutput:
    rebuttal_target_ids: list[str]
    attack_strategy: str
    response_outline: list[str]
    spoken_text: str
    follow_up_questions: list[str]
    evidence_citations: list[str]
    pressure_score: int
    self_check_flags: list[str] = field(default_factory=list)


@dataclass(slots=True)
class CoachReport:
    report_id: str
    session_id: str
    scope: str
    round_verdict: str
    diagnosed_weaknesses: list[dict[str, str]] = field(default_factory=list)
    missed_responses: list[str] = field(default_factory=list)
    logical_fallacies: list[str] = field(default_factory=list)
    score_card: dict[str, int] = field(default_factory=dict)
    improvement_actions: list[str] = field(default_factory=list)
    confidence_notes: list[str] = field(default_factory=list)
    related_turn_ids: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ClosingOutput:
    closing_id: str
    session_id: str
    speaker_side: str
    strategy_summary: str
    outline: list[str] = field(default_factory=list)
    spoken_text: str = ""
    evidence_citations: list[str] = field(default_factory=list)
    confidence_notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class OpeningArgumentCard:
    claim: str
    data_support: str = ""
    academic_support: str = ""
    scenario_support: str = ""


@dataclass(slots=True)
class OpeningFramework:
    judge_standard: str
    framework_summary: str = ""
    argument_cards: list[OpeningArgumentCard] = field(default_factory=list)


@dataclass(slots=True)
class OpeningBrief:
    brief_id: str
    session_id: str
    speaker_side: str
    strategy_summary: str
    outline: list[str] = field(default_factory=list)
    spoken_text: str = ""
    evidence_citations: list[str] = field(default_factory=list)
    confidence_notes: list[str] = field(default_factory=list)
    source_mode: str = "generated"
    framework: OpeningFramework | None = None
    target_duration_minutes: int = 3
    target_word_count: int = 900


@dataclass(slots=True)
class TurnAnalysis:
    summary: str
    arguments: list[ArgumentUnit] = field(default_factory=list)
    clash_points: list[ClashPoint] = field(default_factory=list)
    pending_response_arguments: list[str] = field(default_factory=list)
    model_notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class DebateSession:
    session_id: str
    topic: str
    user_side: str
    agent_side: str
    profile_id: str
    mode: str
    current_phase: DebatePhase
    turn_ids: list[str] = field(default_factory=list)
    active_clash_point_ids: list[str] = field(default_factory=list)
    pending_response_argument_ids: list[str] = field(default_factory=list)
    context_summary: str = ""
    pressure_trend: list[int] = field(default_factory=list)
    options: SessionOptions = field(default_factory=SessionOptions)
    turns: list[TurnRecord] = field(default_factory=list)
    arguments: list[ArgumentUnit] = field(default_factory=list)
    clash_points: list[ClashPoint] = field(default_factory=list)
    coach_reports: list[CoachReport] = field(default_factory=list)
    closing_outputs: list[ClosingOutput] = field(default_factory=list)
    current_opening_framework: OpeningFramework | None = None
    opening_briefs: list[OpeningBrief] = field(default_factory=list)