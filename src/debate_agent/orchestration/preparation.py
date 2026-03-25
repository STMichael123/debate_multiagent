from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from debate_agent.domain.models import DebateProfile, DebateSession, EvidenceRecord, PreparationPacket, TheoryPoint
from debate_agent.infrastructure.llm_client import DebateLLMClient
from debate_agent.retrieval.evidence_service import EvidenceService


@dataclass(slots=True)
class PreparationResult:
    preparation_packet: PreparationPacket
    planner_notes: list[str]
    model_name: str | None = None


class ResearchScoutAgent:
    def __init__(self, evidence_service: EvidenceService) -> None:
        self.evidence_service = evidence_service

    def gather(
        self,
        session: DebateSession,
        focus: str | None = None,
        limit: int = 6,
    ) -> tuple[list[EvidenceRecord], str]:
        latest_turn = focus or (session.turns[-1].raw_text if session.turns else session.topic)
        result = self.evidence_service.retrieve(
            topic=session.topic,
            latest_user_turn=latest_turn,
            clash_points=session.clash_points,
            limit=limit,
            enable_web_search=session.options.web_search_enabled,
        )
        return result.records, result.research_query


class TheorySynthesisAgent:
    def __init__(self, llm_client: DebateLLMClient | None = None, model_name: str | None = None) -> None:
        self.llm_client = llm_client
        self.model_name = model_name

    def synthesize(
        self,
        session: DebateSession,
        profile: DebateProfile,
        evidence_records: list[EvidenceRecord],
        preparation_goal: str,
    ) -> tuple[list[TheoryPoint], list[str], list[str], str, str | None]:
        if self.llm_client is None:
            return self._fallback_synthesis(session, profile, evidence_records, preparation_goal), None

        prompt = self._build_prompt(session, profile, evidence_records, preparation_goal)
        try:
            payload, response = self.llm_client.parse_json(prompt, model=self.model_name)
            return self._parse_payload(payload, evidence_records), response.model
        except RuntimeError:
            return self._fallback_synthesis(session, profile, evidence_records, preparation_goal), None

    def _build_prompt(
        self,
        session: DebateSession,
        profile: DebateProfile,
        evidence_records: list[EvidenceRecord],
        preparation_goal: str,
    ) -> str:
        evidence_lines = "\n".join(
            f"- [{record.evidence_id}] {record.title}: {record.snippet}"
            for record in evidence_records[:6]
        ) or "- 当前没有可用资料，请优先从学理机制与常识场景出发。"
        return (
            "你现在是备赛阶段的学理整合 agent，请基于资料生成可用于比赛准备的 JSON。\n"
            f"辩题：{session.topic}\n"
            f"裁判标准：{profile.judge_standard}\n"
            f"备赛目标：{preparation_goal}\n"
            "可用资料：\n"
            f"{evidence_lines}\n"
            "请严格输出 JSON，字段包括：theory_points、argument_seeds、counterplay_risks、recommended_opening_frame、confidence_notes。"
        )

    def _parse_payload(self, payload: dict[str, object], evidence_records: list[EvidenceRecord]) -> tuple[list[TheoryPoint], list[str], list[str], str, list[str]]:
        evidence_ids = {record.evidence_id for record in evidence_records}
        raw_theory_points = payload.get("theory_points", [])
        theory_points: list[TheoryPoint] = []
        if isinstance(raw_theory_points, list):
            for item in raw_theory_points[:4]:
                if not isinstance(item, dict):
                    continue
                theory_points.append(
                    TheoryPoint(
                        label=_ensure_str(item.get("label"), default="学理抓手"),
                        mechanism=_ensure_str(item.get("mechanism"), default="未说明机制。"),
                        debate_value=_ensure_str(item.get("debate_value")),
                        source_evidence_ids=[evidence_id for evidence_id in _ensure_list(item.get("source_evidence_ids")) if evidence_id in evidence_ids],
                    )
                )
        if not theory_points:
            fallback, _, _, _, _ = self._fallback_synthesis_payload(evidence_records)
            theory_points = fallback
        argument_seeds = _ensure_list(payload.get("argument_seeds"))
        counterplay_risks = _ensure_list(payload.get("counterplay_risks"))
        recommended_opening_frame = _ensure_str(payload.get("recommended_opening_frame"), default="先立判准，再用机制论证和资料支撑主张。")
        confidence_notes = _ensure_list(payload.get("confidence_notes"))
        if not argument_seeds or not counterplay_risks:
            fallback_theory, fallback_seeds, fallback_risks, fallback_frame, fallback_notes = self._fallback_synthesis_payload(evidence_records)
            theory_points = theory_points or fallback_theory
            argument_seeds = argument_seeds or fallback_seeds
            counterplay_risks = counterplay_risks or fallback_risks
            if not recommended_opening_frame.strip():
                recommended_opening_frame = fallback_frame
            confidence_notes = confidence_notes or fallback_notes
        return theory_points, argument_seeds, counterplay_risks, recommended_opening_frame, confidence_notes

    def _fallback_synthesis(
        self,
        session: DebateSession,
        profile: DebateProfile,
        evidence_records: list[EvidenceRecord],
        preparation_goal: str,
    ) -> tuple[list[TheoryPoint], list[str], list[str], str, list[str]]:
        _ = session, profile, preparation_goal
        return self._fallback_synthesis_payload(evidence_records)

    def _fallback_synthesis_payload(self, evidence_records: list[EvidenceRecord]) -> tuple[list[TheoryPoint], list[str], list[str], str, list[str]]:
        theory_points: list[TheoryPoint] = []
        for record in evidence_records[:3]:
            theory_points.append(
                TheoryPoint(
                    label=record.title[:20] or "资料抓手",
                    mechanism=f"可从“{record.snippet[:60]}”提炼机制，说明制度、行为或资源如何影响辩题结果。",
                    debate_value="把资料转成因果链，而不是只堆事实。",
                    source_evidence_ids=[record.evidence_id],
                )
            )
        if not theory_points:
            theory_points = [
                TheoryPoint(
                    label="机制优先",
                    mechanism="先说明制度或行为机制如何作用，再补资料和场景，避免只喊价值口号。",
                    debate_value="适合在没有硬数据时稳住论证结构。",
                    source_evidence_ids=[],
                )
            ]
        argument_seeds = [
            "先锁定裁判标准，再证明本方方案在必要性与净收益上更完整。",
            "把资料转化成‘为什么会发生’的机制链，而不是只报结论。",
            "准备一个学理机制和一个现实场景，形成双支撑结构。",
        ]
        counterplay_risks = [
            "对手会追问资料能否直接推出制度结论，需要提前补上机制桥梁。",
            "对手会追打执行成本或替代方案比较，不能只证明目标正确。",
            "如果资料来源位阶不高，必须准备学理和场景补强。",
        ]
        recommended_opening_frame = "先立裁判标准，再给出两到三个核心论点，每个论点都配一个机制说明和一条资料或场景支撑。"
        confidence_notes = ["当前为 preparation fallback 摘要，可继续人工筛选最强资料。"]
        return theory_points, argument_seeds, counterplay_risks, recommended_opening_frame, confidence_notes


class PreparationCoordinator:
    def __init__(
        self,
        research_scout: ResearchScoutAgent,
        theory_synthesis_agent: TheorySynthesisAgent,
    ) -> None:
        self.research_scout = research_scout
        self.theory_synthesis_agent = theory_synthesis_agent

    def prepare(
        self,
        session: DebateSession,
        profile: DebateProfile,
        preparation_goal: str,
        focus: str | None = None,
        limit: int = 6,
    ) -> PreparationResult:
        evidence_records, research_query = self.research_scout.gather(session=session, focus=focus, limit=limit)
        theory_points, argument_seeds, counterplay_risks, recommended_opening_frame, confidence_notes, model_name = self._synthesize(
            session=session,
            profile=profile,
            evidence_records=evidence_records,
            preparation_goal=preparation_goal,
        )
        planner_notes = [
            "先完成资料筛选，再做学理整合，避免比赛链路直接承担备赛职责。",
            f"本次备赛共整理 {len(evidence_records)} 条资料，形成 {len(theory_points)} 个学理抓手。",
        ]
        packet = PreparationPacket(
            packet_id=str(uuid4()),
            session_id=session.session_id,
            topic=session.topic,
            research_query=research_query,
            evidence_records=evidence_records,
            theory_points=theory_points,
            argument_seeds=argument_seeds,
            counterplay_risks=counterplay_risks,
            recommended_opening_frame=recommended_opening_frame,
            confidence_notes=confidence_notes,
        )
        return PreparationResult(preparation_packet=packet, planner_notes=planner_notes, model_name=model_name)

    def _synthesize(
        self,
        session: DebateSession,
        profile: DebateProfile,
        evidence_records: list[EvidenceRecord],
        preparation_goal: str,
    ) -> tuple[list[TheoryPoint], list[str], list[str], str, list[str], str | None]:
        result, model_name = self.theory_synthesis_agent.synthesize(
            session=session,
            profile=profile,
            evidence_records=evidence_records,
            preparation_goal=preparation_goal,
        )
        theory_points, argument_seeds, counterplay_risks, recommended_opening_frame, confidence_notes = result
        return theory_points, argument_seeds, counterplay_risks, recommended_opening_frame, confidence_notes, model_name


def _ensure_str(value: object, default: str = "") -> str:
    if isinstance(value, str):
        return value.strip() or default
    if value is None:
        return default
    return str(value).strip() or default


def _ensure_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        normalized = _ensure_str(item)
        if normalized:
            result.append(normalized)
    return result