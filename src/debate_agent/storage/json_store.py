from __future__ import annotations

import json
import os
import shutil
import tempfile
from dataclasses import asdict
from pathlib import Path

from debate_agent.domain.models import ArgumentUnit, ClashPoint, ClosingOutput, CoachFeedbackMode, CoachReport, DebatePhase, DebateSession, EvidenceRecord, InquiryOutput, OpeningArgumentCard, OpeningBrief, OpeningFramework, PreparationPacket, SessionOptions, SpeakerRole, TheoryPoint, TimerPlan, TurnRecord

_MAX_BACKUPS_PER_SESSION = 5


class JSONSessionStore:
    def __init__(self, session_dir: Path | None = None) -> None:
        self.session_dir = session_dir or self._default_session_dir()
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self._backup_dir = self.session_dir / ".backup"
        self._backup_dir.mkdir(parents=True, exist_ok=True)

    def save_session(self, session: DebateSession) -> Path:
        file_path = self.session_dir / f"{session.session_id}.json"
        self._backup_if_exists(file_path)
        payload = asdict(session)
        content = json.dumps(payload, ensure_ascii=False, indent=2)
        fd, tmp_path = tempfile.mkstemp(
            suffix=".tmp",
            prefix=f"{session.session_id}_",
            dir=str(self.session_dir),
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as tmp_file:
                tmp_file.write(content)
                tmp_file.flush()
                os.fsync(tmp_file.fileno())
            os.replace(tmp_path, str(file_path))
        except BaseException:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
        return file_path

    def _backup_if_exists(self, file_path: Path) -> None:
        if not file_path.exists():
            return
        import time
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        backup_name = f"{file_path.stem}_{timestamp}.json"
        backup_path = self._backup_dir / backup_name
        shutil.copy2(str(file_path), str(backup_path))
        self._prune_backups(file_path.stem)

    def _prune_backups(self, session_id: str) -> None:
        backups = sorted(
            self._backup_dir.glob(f"{session_id}_*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for old_backup in backups[_MAX_BACKUPS_PER_SESSION:]:
            old_backup.unlink(missing_ok=True)

    def load_session(self, session_id: str) -> DebateSession:
        file_path = self.session_dir / f"{session_id}.json"
        payload = json.loads(file_path.read_text(encoding="utf-8"))
        return self._build_session(payload)

    def list_session_ids(self) -> list[str]:
        return sorted(file_path.stem for file_path in self.session_dir.glob("*.json"))

    def delete_session(self, session_id: str) -> Path:
        file_path = self.session_dir / f"{session_id}.json"
        file_path.unlink()
        return file_path

    def _build_session(self, payload: dict[str, object]) -> DebateSession:
        turns = [self._build_turn(item) for item in self._ensure_list_of_dicts(payload.get("turns"))]
        arguments = [self._build_argument(item) for item in self._ensure_list_of_dicts(payload.get("arguments"))]
        clash_points = [self._build_clash_point(item) for item in self._ensure_list_of_dicts(payload.get("clash_points"))]
        coach_reports = [self._build_coach_report(item) for item in self._ensure_list_of_dicts(payload.get("coach_reports"))]
        timer_plans = [self._build_timer_plan(item) for item in self._ensure_list_of_dicts(payload.get("timer_plans"))]
        preparation_packets = [self._build_preparation_packet(item) for item in self._ensure_list_of_dicts(payload.get("preparation_packets"))]
        inquiry_outputs = [self._build_inquiry_output(item) for item in self._ensure_list_of_dicts(payload.get("inquiry_outputs"))]
        closing_outputs = [self._build_closing_output(item) for item in self._ensure_list_of_dicts(payload.get("closing_outputs"))]
        opening_briefs = [self._build_opening_brief(item) for item in self._ensure_list_of_dicts(payload.get("opening_briefs"))]
        current_opening_framework = self._build_opening_framework(payload.get("current_opening_framework"))
        return DebateSession(
            session_id=self._ensure_str(payload.get("session_id")),
            topic=self._ensure_str(payload.get("topic")),
            user_side=self._ensure_str(payload.get("user_side")),
            agent_side=self._ensure_str(payload.get("agent_side")),
            profile_id=self._ensure_str(payload.get("profile_id")),
            mode=self._ensure_str(payload.get("mode")),
            current_phase=DebatePhase(self._ensure_str(payload.get("current_phase"), default=DebatePhase.CROSSFIRE.value)),
            turn_ids=self._ensure_list_of_str(payload.get("turn_ids")),
            active_clash_point_ids=self._ensure_list_of_str(payload.get("active_clash_point_ids")),
            pending_response_argument_ids=self._ensure_list_of_str(payload.get("pending_response_argument_ids")),
            context_summary=self._ensure_str(payload.get("context_summary")),
            pressure_trend=self._ensure_list_of_int(payload.get("pressure_trend")),
            options=self._build_session_options(payload.get("options")),
            turns=turns,
            arguments=arguments,
            clash_points=clash_points,
            coach_reports=coach_reports,
            timer_plans=timer_plans,
            preparation_packets=preparation_packets,
            inquiry_outputs=inquiry_outputs,
            closing_outputs=closing_outputs,
            current_opening_framework=current_opening_framework,
            opening_briefs=opening_briefs,
        )

    def _build_session_options(self, payload: object) -> SessionOptions:
        options_payload = payload if isinstance(payload, dict) else {}
        coach_mode = self._ensure_str(options_payload.get("coach_feedback_mode"), default=CoachFeedbackMode.MANUAL.value)
        if coach_mode not in {CoachFeedbackMode.MANUAL.value, CoachFeedbackMode.AUTO.value}:
            coach_mode = CoachFeedbackMode.MANUAL.value
        return SessionOptions(
            coach_feedback_mode=CoachFeedbackMode(coach_mode),
            web_search_enabled=self._ensure_bool(options_payload.get("web_search_enabled"), default=True),
            default_closing_side=self._ensure_str(options_payload.get("default_closing_side"), default="opponent") or "opponent",
        )

    def _build_turn(self, payload: dict[str, object]) -> TurnRecord:
        return TurnRecord(
            turn_id=self._ensure_str(payload.get("turn_id")),
            session_id=self._ensure_str(payload.get("session_id")),
            speaker_role=SpeakerRole(self._ensure_str(payload.get("speaker_role"), default=SpeakerRole.USER.value)),
            phase=DebatePhase(self._ensure_str(payload.get("phase"), default=DebatePhase.CROSSFIRE.value)),
            raw_text=self._ensure_str(payload.get("raw_text")),
            normalized_text=self._ensure_str(payload.get("normalized_text")),
            argument_ids=self._ensure_list_of_str(payload.get("argument_ids")),
            targeted_argument_ids=self._ensure_list_of_str(payload.get("targeted_argument_ids")),
            evidence_ids=self._ensure_list_of_str(payload.get("evidence_ids")),
            token_usage=self._ensure_optional_int(payload.get("token_usage")),
            latency_ms=self._ensure_optional_int(payload.get("latency_ms")),
        )

    def _build_argument(self, payload: dict[str, object]) -> ArgumentUnit:
        return ArgumentUnit(
            argument_id=self._ensure_str(payload.get("argument_id")),
            turn_id=self._ensure_str(payload.get("turn_id")),
            speaker_role=SpeakerRole(self._ensure_str(payload.get("speaker_role"), default=SpeakerRole.USER.value)),
            claim=self._ensure_str(payload.get("claim")),
            warrant=self._ensure_str(payload.get("warrant")),
            impact=self._ensure_str(payload.get("impact")),
            argument_type=self._ensure_str(payload.get("argument_type")),
            tags=self._ensure_list_of_str(payload.get("tags")),
            strength_score=self._ensure_optional_float(payload.get("strength_score")),
            status=self._ensure_str(payload.get("status"), default="open"),
            parent_argument_id=self._ensure_optional_str(payload.get("parent_argument_id")),
            attacks_argument_id=self._ensure_optional_str(payload.get("attacks_argument_id")),
        )

    def _build_clash_point(self, payload: dict[str, object]) -> ClashPoint:
        return ClashPoint(
            clash_point_id=self._ensure_str(payload.get("clash_point_id")),
            topic_label=self._ensure_str(payload.get("topic_label")),
            summary=self._ensure_str(payload.get("summary")),
            user_argument_ids=self._ensure_list_of_str(payload.get("user_argument_ids")),
            agent_argument_ids=self._ensure_list_of_str(payload.get("agent_argument_ids")),
            open_questions=self._ensure_list_of_str(payload.get("open_questions")),
            current_pressure_side=self._ensure_str(payload.get("current_pressure_side"), default="neutral"),
            resolution_status=self._ensure_str(payload.get("resolution_status"), default="open"),
            last_updated_turn_id=self._ensure_optional_str(payload.get("last_updated_turn_id")),
        )

    def _build_coach_report(self, payload: dict[str, object]) -> CoachReport:
        score_card_payload = payload.get("score_card")
        score_card = score_card_payload if isinstance(score_card_payload, dict) else {}
        diagnosed_payload = payload.get("diagnosed_weaknesses")
        diagnosed = diagnosed_payload if isinstance(diagnosed_payload, list) else []
        return CoachReport(
            report_id=self._ensure_str(payload.get("report_id")),
            session_id=self._ensure_str(payload.get("session_id")),
            scope=self._ensure_str(payload.get("scope")),
            round_verdict=self._ensure_str(payload.get("round_verdict")),
            diagnosed_weaknesses=[{str(key): self._ensure_str(value) for key, value in item.items()} for item in diagnosed if isinstance(item, dict)],
            missed_responses=self._ensure_list_of_str(payload.get("missed_responses")),
            logical_fallacies=self._ensure_list_of_str(payload.get("logical_fallacies")),
            score_card={str(key): self._ensure_optional_int(value) or 0 for key, value in score_card.items()},
            improvement_actions=self._ensure_list_of_str(payload.get("improvement_actions")),
            confidence_notes=self._ensure_list_of_str(payload.get("confidence_notes")),
            related_turn_ids=self._ensure_list_of_str(payload.get("related_turn_ids")),
        )

    def _build_closing_output(self, payload: dict[str, object]) -> ClosingOutput:
        return ClosingOutput(
            closing_id=self._ensure_str(payload.get("closing_id")),
            session_id=self._ensure_str(payload.get("session_id")),
            speaker_side=self._ensure_str(payload.get("speaker_side")),
            strategy_summary=self._ensure_str(payload.get("strategy_summary")),
            outline=self._ensure_list_of_str(payload.get("outline")),
            spoken_text=self._ensure_str(payload.get("spoken_text")),
            evidence_citations=self._ensure_list_of_str(payload.get("evidence_citations")),
            confidence_notes=self._ensure_list_of_str(payload.get("confidence_notes")),
        )

    def _build_inquiry_output(self, payload: dict[str, object]) -> InquiryOutput:
        return InquiryOutput(
            inquiry_id=self._ensure_str(payload.get("inquiry_id")),
            session_id=self._ensure_str(payload.get("session_id")),
            speaker_side=self._ensure_str(payload.get("speaker_side")),
            strategy_summary=self._ensure_str(payload.get("strategy_summary")),
            target_clash_points=self._ensure_list_of_str(payload.get("target_clash_points")),
            priority_targets=self._ensure_list_of_str(payload.get("priority_targets")),
            questions=self._ensure_list_of_str(payload.get("questions")),
            spoken_text=self._ensure_str(payload.get("spoken_text")),
            evidence_citations=self._ensure_list_of_str(payload.get("evidence_citations")),
            confidence_notes=self._ensure_list_of_str(payload.get("confidence_notes")),
        )

    def _build_timer_plan(self, payload: dict[str, object]) -> TimerPlan:
        return TimerPlan(
            timer_id=self._ensure_str(payload.get("timer_id")),
            session_id=self._ensure_str(payload.get("session_id")),
            phase=DebatePhase(self._ensure_str(payload.get("phase"), default=DebatePhase.CROSSFIRE.value)),
            speaker_side=self._ensure_str(payload.get("speaker_side")),
            allocated_seconds=self._ensure_optional_int(payload.get("allocated_seconds")) or 0,
            warning_threshold_seconds=self._ensure_optional_int(payload.get("warning_threshold_seconds")) or 0,
            status=self._ensure_str(payload.get("status"), default="planned"),
            source=self._ensure_str(payload.get("source"), default="automation"),
            notes=self._ensure_list_of_str(payload.get("notes")),
        )

    def _build_preparation_packet(self, payload: dict[str, object]) -> PreparationPacket:
        evidence_records = [self._build_evidence_record(item) for item in self._ensure_list_of_dicts(payload.get("evidence_records"))]
        theory_points = [self._build_theory_point(item) for item in self._ensure_list_of_dicts(payload.get("theory_points"))]
        return PreparationPacket(
            packet_id=self._ensure_str(payload.get("packet_id")),
            session_id=self._ensure_str(payload.get("session_id")),
            topic=self._ensure_str(payload.get("topic")),
            research_query=self._ensure_str(payload.get("research_query")),
            evidence_records=evidence_records,
            theory_points=theory_points,
            argument_seeds=self._ensure_list_of_str(payload.get("argument_seeds")),
            counterplay_risks=self._ensure_list_of_str(payload.get("counterplay_risks")),
            recommended_opening_frame=self._ensure_str(payload.get("recommended_opening_frame")),
            source_mode=self._ensure_str(payload.get("source_mode"), default="prepared"),
            confidence_notes=self._ensure_list_of_str(payload.get("confidence_notes")),
        )

    def _build_evidence_record(self, payload: dict[str, object]) -> EvidenceRecord:
        return EvidenceRecord(
            evidence_id=self._ensure_str(payload.get("evidence_id")),
            query_text=self._ensure_str(payload.get("query_text")),
            source_type=self._ensure_str(payload.get("source_type")),
            source_ref=self._ensure_str(payload.get("source_ref")),
            title=self._ensure_str(payload.get("title")),
            snippet=self._ensure_str(payload.get("snippet")),
            stance_hint=self._ensure_str(payload.get("stance_hint")),
            relevance_score=self._ensure_optional_float(payload.get("relevance_score")),
            credibility_score=self._ensure_optional_float(payload.get("credibility_score")),
            used_by_turn_ids=self._ensure_list_of_str(payload.get("used_by_turn_ids")),
            verification_state=self._ensure_str(payload.get("verification_state"), default="unverified"),
        )

    def _build_theory_point(self, payload: dict[str, object]) -> TheoryPoint:
        return TheoryPoint(
            label=self._ensure_str(payload.get("label")),
            mechanism=self._ensure_str(payload.get("mechanism")),
            debate_value=self._ensure_str(payload.get("debate_value")),
            source_evidence_ids=self._ensure_list_of_str(payload.get("source_evidence_ids")),
        )

    def _build_opening_brief(self, payload: dict[str, object]) -> OpeningBrief:
        framework_payload = payload.get("framework")
        return OpeningBrief(
            brief_id=self._ensure_str(payload.get("brief_id")),
            session_id=self._ensure_str(payload.get("session_id")),
            speaker_side=self._ensure_str(payload.get("speaker_side")),
            strategy_summary=self._ensure_str(payload.get("strategy_summary")),
            outline=self._ensure_list_of_str(payload.get("outline")),
            spoken_text=self._ensure_str(payload.get("spoken_text")),
            evidence_citations=self._ensure_list_of_str(payload.get("evidence_citations")),
            confidence_notes=self._ensure_list_of_str(payload.get("confidence_notes")),
            source_mode=self._ensure_str(payload.get("source_mode"), default="generated"),
            framework=self._build_opening_framework(framework_payload),
            target_duration_minutes=self._ensure_optional_int(payload.get("target_duration_minutes")) or 3,
            target_word_count=self._ensure_optional_int(payload.get("target_word_count")) or 900,
        )

    def _build_opening_framework(self, payload: object) -> OpeningFramework | None:
        if not isinstance(payload, dict):
            return None
        cards_payload = payload.get("argument_cards")
        cards = [self._build_opening_argument_card(item) for item in self._ensure_list_of_dicts(cards_payload)]
        return OpeningFramework(
            judge_standard=self._ensure_str(payload.get("judge_standard")),
            framework_summary=self._ensure_str(payload.get("framework_summary")),
            argument_cards=cards,
        )

    def _build_opening_argument_card(self, payload: dict[str, object]) -> OpeningArgumentCard:
        return OpeningArgumentCard(
            claim=self._ensure_str(payload.get("claim")),
            data_support=self._ensure_str(payload.get("data_support")),
            academic_support=self._ensure_str(payload.get("academic_support")),
            scenario_support=self._ensure_str(payload.get("scenario_support")),
        )

    def _ensure_list_of_dicts(self, value: object) -> list[dict[str, object]]:
        if not isinstance(value, list):
            return []
        return [item for item in value if isinstance(item, dict)]

    def _ensure_list_of_str(self, value: object) -> list[str]:
        if not isinstance(value, list):
            return []
        return [self._ensure_str(item) for item in value if self._ensure_str(item)]

    def _ensure_list_of_int(self, value: object) -> list[int]:
        if not isinstance(value, list):
            return []
        result: list[int] = []
        for item in value:
            parsed = self._ensure_optional_int(item)
            if parsed is not None:
                result.append(parsed)
        return result

    def _ensure_str(self, value: object, default: str = "") -> str:
        if isinstance(value, str):
            return value
        if value is None:
            return default
        return str(value)

    def _ensure_optional_str(self, value: object) -> str | None:
        text = self._ensure_str(value).strip()
        return text or None

    def _ensure_optional_int(self, value: object) -> int | None:
        try:
            return int(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None

    def _ensure_optional_float(self, value: object) -> float | None:
        try:
            return float(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None

    def _ensure_bool(self, value: object, default: bool) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"true", "1", "yes", "on"}:
                return True
            if normalized in {"false", "0", "no", "off"}:
                return False
        return default

    def _default_session_dir(self) -> Path:
        return Path(__file__).resolve().parents[3] / "data" / "sessions"