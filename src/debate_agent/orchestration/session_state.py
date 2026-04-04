from __future__ import annotations

import time
from uuid import uuid4

from debate_agent.domain.models import AgentOutput, ArgumentUnit, ClashPoint, ClosingOutput, CoachReport, DebateSession, EvidenceRecord, EvidenceWorkbenchState, InquiryOutput, OpeningBrief, OpeningFramework, OpeningFrameworkVersion, PreparationPacket, SpeakerRole, TimerPlan, TurnAnalysis, TurnRecord


class SessionStateMutator:
    def create_user_turn(self, session: DebateSession, user_text: str) -> TurnRecord:
        turn_id = str(uuid4())
        return TurnRecord(
            turn_id=turn_id,
            session_id=session.session_id,
            speaker_role=SpeakerRole.USER,
            phase=session.current_phase,
            raw_text=user_text,
            normalized_text=user_text.strip(),
        )

    def create_opponent_turn(
        self,
        session: DebateSession,
        opponent_output: AgentOutput,
        target_argument_ids: list[str],
    ) -> tuple[TurnRecord, list[ArgumentUnit]]:
        turn_id = str(uuid4())
        opponent_turn = TurnRecord(
            turn_id=turn_id,
            session_id=session.session_id,
            speaker_role=SpeakerRole.OPPONENT,
            phase=session.current_phase,
            raw_text=opponent_output.spoken_text,
            normalized_text=opponent_output.spoken_text.strip(),
            targeted_argument_ids=target_argument_ids,
            evidence_ids=opponent_output.evidence_citations,
        )
        arguments: list[ArgumentUnit] = []
        outlines = opponent_output.response_outline or [opponent_output.spoken_text]
        for index, outline in enumerate(outlines[:3], start=1):
            arguments.append(
                ArgumentUnit(
                    argument_id=f"opp-{turn_id}-{index}",
                    turn_id=turn_id,
                    speaker_role=SpeakerRole.OPPONENT,
                    claim=outline,
                    warrant=opponent_output.attack_strategy,
                    impact="迫使用户回应当前核心 clash。",
                    argument_type="rebuttal",
                    tags=["opponent_attack"],
                    strength_score=float(opponent_output.pressure_score),
                    attacks_argument_id=target_argument_ids[0] if target_argument_ids else None,
                )
            )
        opponent_turn.argument_ids = [item.argument_id for item in arguments]
        return opponent_turn, arguments

    def apply_turn_result(
        self,
        session: DebateSession,
        user_turn: TurnRecord,
        turn_analysis: TurnAnalysis,
        clash_points: list[ClashPoint],
        opponent_turn: TurnRecord,
        opponent_arguments: list[ArgumentUnit],
        pending_response_argument_ids: list[str],
        pressure_score: int,
        coach_report: CoachReport | None = None,
    ) -> None:
        session.turn_ids.extend([user_turn.turn_id, opponent_turn.turn_id])
        session.turns.extend([user_turn, opponent_turn])
        session.arguments.extend(turn_analysis.arguments)
        session.arguments.extend(opponent_arguments)
        self.attach_opponent_arguments_to_clash_points(clash_points, opponent_arguments)
        session.clash_points = clash_points
        session.active_clash_point_ids = [item.clash_point_id for item in clash_points if item.resolution_status == "open"]
        session.pending_response_argument_ids = pending_response_argument_ids
        session.context_summary = self.merge_context_summary(session.context_summary, turn_analysis.summary, opponent_turn.normalized_text)
        session.pressure_trend.append(pressure_score)
        if coach_report is not None:
            self.upsert_coach_report(session, coach_report)

    def upsert_coach_report(self, session: DebateSession, coach_report: CoachReport) -> None:
        if session.coach_reports and session.coach_reports[-1].related_turn_ids == coach_report.related_turn_ids:
            session.coach_reports[-1] = coach_report
            return
        session.coach_reports.append(coach_report)

    def add_closing_output(self, session: DebateSession, closing_output: ClosingOutput) -> None:
        session.closing_outputs.append(closing_output)

    def add_inquiry_output(self, session: DebateSession, inquiry_output: InquiryOutput) -> None:
        session.inquiry_outputs.append(inquiry_output)

    def add_timer_plan(self, session: DebateSession, timer_plan: TimerPlan) -> None:
        session.timer_plans.append(timer_plan)

    def add_preparation_packet(self, session: DebateSession, preparation_packet: PreparationPacket) -> None:
        session.preparation_packets.append(preparation_packet)

    def add_opening_brief(self, session: DebateSession, opening_brief: OpeningBrief) -> None:
        if opening_brief.created_at <= 0:
            opening_brief.created_at = time.time()
        session.opening_briefs.append(opening_brief)
        session.current_opening_brief_id = opening_brief.brief_id
        if opening_brief.framework is not None:
            session.current_opening_framework = opening_brief.framework

    def set_opening_framework(
        self,
        session: DebateSession,
        framework: OpeningFramework | None,
        source_mode: str = "generated",
        label: str = "",
    ) -> None:
        session.current_opening_framework = framework
        session.current_opening_brief_id = None
        if framework is None:
            session.current_opening_framework_version_id = None
            return

        version = OpeningFrameworkVersion(
            version_id=str(uuid4()),
            session_id=session.session_id,
            framework=framework,
            created_at=time.time(),
            source_mode=source_mode,
            label=label,
        )
        session.opening_framework_versions.append(version)
        session.current_opening_framework_version_id = version.version_id

    def current_opening_framework(self, session: DebateSession) -> OpeningFramework | None:
        return session.current_opening_framework

    def current_opening_brief(self, session: DebateSession) -> OpeningBrief | None:
        if session.current_opening_brief_id:
            for opening_brief in reversed(session.opening_briefs):
                if opening_brief.brief_id == session.current_opening_brief_id:
                    return opening_brief
        if not session.opening_briefs:
            return None
        return session.opening_briefs[-1]

    def opening_brief_by_id(self, session: DebateSession, brief_id: str) -> OpeningBrief | None:
        for opening_brief in session.opening_briefs:
            if opening_brief.brief_id == brief_id:
                return opening_brief
        return None

    def opening_framework_version_by_id(self, session: DebateSession, version_id: str) -> OpeningFrameworkVersion | None:
        for version in session.opening_framework_versions:
            if version.version_id == version_id:
                return version
        return None

    def ensure_evidence_workbench(self, session: DebateSession) -> EvidenceWorkbenchState:
        if session.evidence_workbench is None:
            session.evidence_workbench = EvidenceWorkbenchState(session_id=session.session_id)
        return session.evidence_workbench

    def apply_evidence_workbench(
        self,
        session: DebateSession,
        evidence_records: list[EvidenceRecord],
        research_query: str | None = None,
    ) -> list[EvidenceRecord]:
        workbench = self.ensure_evidence_workbench(session)
        blacklisted = {item.strip() for item in workbench.blacklisted_source_types if item.strip()}

        filtered_live = [
            self._clone_evidence(item, is_pinned=self._is_pinned(workbench, item.evidence_id))
            for item in evidence_records
            if item.source_type not in blacklisted
        ]
        pinned_records = [self._clone_evidence(item, is_pinned=True) for item in workbench.pinned_evidence]
        user_supplied_records = [
            self._clone_evidence(item, is_pinned=self._is_pinned(workbench, item.evidence_id))
            for item in workbench.user_supplied_evidence
            if item.source_type not in blacklisted or item.is_pinned
        ]

        available = self._dedupe_evidence_records([*pinned_records, *user_supplied_records, *filtered_live])
        workbench.available_evidence = available
        workbench.last_research_query = (research_query or "").strip()
        return available

    def pin_evidence(self, session: DebateSession, evidence_id: str) -> None:
        workbench = self.ensure_evidence_workbench(session)
        if self._is_pinned(workbench, evidence_id):
            return
        evidence = self._find_evidence(workbench, evidence_id)
        if evidence is None:
            raise ValueError("指定的证据不存在，无法钉住。")
        workbench.pinned_evidence.append(self._clone_evidence(evidence, is_pinned=True))
        self.apply_evidence_workbench(session, workbench.available_evidence, workbench.last_research_query)

    def unpin_evidence(self, session: DebateSession, evidence_id: str) -> None:
        workbench = self.ensure_evidence_workbench(session)
        workbench.pinned_evidence = [item for item in workbench.pinned_evidence if item.evidence_id != evidence_id]
        self.apply_evidence_workbench(session, workbench.available_evidence, workbench.last_research_query)

    def blacklist_source_type(self, session: DebateSession, source_type: str) -> None:
        workbench = self.ensure_evidence_workbench(session)
        normalized = source_type.strip()
        if not normalized:
            raise ValueError("source_type 不能为空。")
        if normalized not in workbench.blacklisted_source_types:
            workbench.blacklisted_source_types.append(normalized)
        self.apply_evidence_workbench(session, workbench.available_evidence, workbench.last_research_query)

    def remove_blacklisted_source_type(self, session: DebateSession, source_type: str) -> None:
        workbench = self.ensure_evidence_workbench(session)
        workbench.blacklisted_source_types = [item for item in workbench.blacklisted_source_types if item != source_type]
        self.apply_evidence_workbench(session, workbench.available_evidence, workbench.last_research_query)

    def add_user_supplied_evidence(self, session: DebateSession, evidence_record: EvidenceRecord) -> None:
        workbench = self.ensure_evidence_workbench(session)
        workbench.user_supplied_evidence = self._dedupe_evidence_records([*workbench.user_supplied_evidence, evidence_record])
        self.apply_evidence_workbench(session, workbench.available_evidence, workbench.last_research_query)

    def update_evidence_explanation(self, session: DebateSession, evidence_id: str, explanation: str) -> None:
        workbench = self.ensure_evidence_workbench(session)
        normalized = explanation.strip()
        updated = False
        for collection in [workbench.available_evidence, workbench.pinned_evidence, workbench.user_supplied_evidence]:
            for evidence in collection:
                if evidence.evidence_id == evidence_id:
                    evidence.user_explanation = normalized
                    updated = True
        if not updated:
            raise ValueError("指定的证据不存在，无法更新备注。")
        self.apply_evidence_workbench(session, workbench.available_evidence, workbench.last_research_query)

    def latest_exchange_turns(self, session: DebateSession) -> tuple[TurnRecord | None, TurnRecord | None]:
        latest_user_turn: TurnRecord | None = None
        latest_opponent_turn: TurnRecord | None = None
        for turn in reversed(session.turns):
            if latest_opponent_turn is None and turn.speaker_role == SpeakerRole.OPPONENT:
                latest_opponent_turn = turn
                continue
            if latest_user_turn is None and turn.speaker_role == SpeakerRole.USER:
                latest_user_turn = turn
            if latest_user_turn is not None and latest_opponent_turn is not None:
                break
        return latest_user_turn, latest_opponent_turn

    def latest_exchange_turn_ids(self, session: DebateSession) -> list[str]:
        latest_user_turn, latest_opponent_turn = self.latest_exchange_turns(session)
        result: list[str] = []
        if latest_user_turn is not None:
            result.append(latest_user_turn.turn_id)
        if latest_opponent_turn is not None:
            result.append(latest_opponent_turn.turn_id)
        return result

    def merge_context_summary(self, previous_summary: str, user_summary: str, opponent_text: str) -> str:
        opponent_summary = opponent_text.strip()
        fragments = [fragment for fragment in [previous_summary, user_summary, f"对手最新回应：{opponent_summary}"] if fragment]
        if len(fragments) <= 2:
            return "\n".join(fragments)
        return "\n".join(fragments[-3:])

    def merge_clash_points(self, session: DebateSession, new_clash_points: list[ClashPoint]) -> list[ClashPoint]:
        if not session.clash_points:
            return new_clash_points

        existing_by_label = {self._normalize_label(item.topic_label): item for item in session.clash_points}
        merged = list(session.clash_points)
        for new_clash in new_clash_points:
            key = self._normalize_label(new_clash.topic_label)
            existing = existing_by_label.get(key)
            if existing is None:
                merged.append(new_clash)
                existing_by_label[key] = new_clash
                continue

            existing.summary = new_clash.summary or existing.summary
            existing.user_argument_ids = self._dedupe(existing.user_argument_ids + new_clash.user_argument_ids)
            existing.agent_argument_ids = self._dedupe(existing.agent_argument_ids + new_clash.agent_argument_ids)
            existing.open_questions = self._dedupe(existing.open_questions + new_clash.open_questions)
            existing.current_pressure_side = new_clash.current_pressure_side or existing.current_pressure_side
            existing.last_updated_turn_id = new_clash.last_updated_turn_id or existing.last_updated_turn_id
        return merged

    def attach_opponent_arguments_to_clash_points(
        self,
        clash_points: list[ClashPoint],
        opponent_arguments: list[ArgumentUnit],
    ) -> None:
        if not clash_points or not opponent_arguments:
            return

        for argument in opponent_arguments:
            attached = False
            for clash in clash_points:
                if argument.attacks_argument_id and argument.attacks_argument_id in clash.user_argument_ids:
                    clash.agent_argument_ids = self._dedupe(clash.agent_argument_ids + [argument.argument_id])
                    clash.current_pressure_side = "opponent"
                    clash.last_updated_turn_id = argument.turn_id
                    attached = True
            if not attached:
                clash_points[0].agent_argument_ids = self._dedupe(clash_points[0].agent_argument_ids + [argument.argument_id])
                clash_points[0].current_pressure_side = "opponent"
                clash_points[0].last_updated_turn_id = argument.turn_id

    def _normalize_label(self, label: str) -> str:
        return "".join(label.lower().split())

    def _dedupe(self, items: list[str]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for item in items:
            normalized = item.strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            result.append(normalized)
        return result

    def _dedupe_evidence_records(self, records: list[EvidenceRecord]) -> list[EvidenceRecord]:
        result: list[EvidenceRecord] = []
        seen: set[str] = set()
        for item in records:
            dedupe_key = item.evidence_id or f"{item.source_ref}|{item.title}|{item.snippet}"
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            result.append(item)
        return result

    def _is_pinned(self, workbench: EvidenceWorkbenchState, evidence_id: str) -> bool:
        return any(item.evidence_id == evidence_id for item in workbench.pinned_evidence)

    def _find_evidence(self, workbench: EvidenceWorkbenchState, evidence_id: str) -> EvidenceRecord | None:
        for collection in [workbench.available_evidence, workbench.user_supplied_evidence, workbench.pinned_evidence]:
            for item in collection:
                if item.evidence_id == evidence_id:
                    return item
        return None

    def _clone_evidence(self, evidence: EvidenceRecord, is_pinned: bool | None = None) -> EvidenceRecord:
        return EvidenceRecord(
            evidence_id=evidence.evidence_id,
            query_text=evidence.query_text,
            source_type=evidence.source_type,
            source_ref=evidence.source_ref,
            title=evidence.title,
            snippet=evidence.snippet,
            stance_hint=evidence.stance_hint,
            relevance_score=evidence.relevance_score,
            credibility_score=evidence.credibility_score,
            used_by_turn_ids=list(evidence.used_by_turn_ids),
            verification_state=evidence.verification_state,
            user_explanation=evidence.user_explanation,
            is_pinned=evidence.is_pinned if is_pinned is None else is_pinned,
        )