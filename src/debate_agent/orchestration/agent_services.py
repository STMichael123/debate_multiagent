from __future__ import annotations

from dataclasses import dataclass
import re
import time
from typing import Callable
from uuid import uuid4

from debate_agent.domain.models import AgentOutput, ArgumentUnit, ClashPoint, ClosingOutput, CoachReport, DebateProfile, DebateSession, EvidenceRecord, OpeningArgumentCard, OpeningBrief, OpeningFramework, SpeakerRole, TurnAnalysis, TurnRecord
from debate_agent.infrastructure.llm_client import DebateLLMClient
from debate_agent.prompts.builders import build_closing_variables, build_coach_variables, build_opening_coach_variables, build_opening_draft_variables, build_opening_variables, build_opponent_variables
from debate_agent.prompts.templates import ARGUMENT_ANALYSIS_TEMPLATE, CLOSING_TEMPLATE, COACH_TEMPLATE, OPENING_COACH_TEMPLATE, OPENING_DRAFT_STREAM_TEMPLATE, OPENING_DRAFT_TEMPLATE, OPENING_FRAMEWORK_TEMPLATE, OPPONENT_TEMPLATE


@dataclass(slots=True)
class CoachGenerationResult:
    coach_report: CoachReport
    prompt: str | None
    model_name: str | None = None
    used_cached: bool = False


@dataclass(slots=True)
class ClosingGenerationResult:
    closing_output: ClosingOutput
    prompt: str
    model_name: str | None = None


@dataclass(slots=True)
class OpeningGenerationResult:
    opening_brief: OpeningBrief
    prompt: str
    model_name: str | None = None


@dataclass(slots=True)
class OpeningFrameworkGenerationResult:
    framework: OpeningFramework
    prompt: str
    model_name: str | None = None


class TurnAnalyzer:
    def __init__(self, llm_client: DebateLLMClient | None = None) -> None:
        self.llm_client = llm_client

    def analyze(
        self,
        session: DebateSession,
        profile: DebateProfile,
        user_turn: TurnRecord,
    ) -> tuple[TurnAnalysis, str]:
        prompt = ARGUMENT_ANALYSIS_TEMPLATE.render(
            {
                "topic": session.topic,
                "debate_type": profile.debate_type.value,
                "user_side": session.user_side,
                "agent_side": session.agent_side,
                "current_phase": session.current_phase.value,
                "judge_standard": profile.judge_standard,
                "burden_rules": "；".join(profile.burden_rules),
                "recent_turns_summary": session.context_summary or "暂无历史摘要。",
                "latest_user_turn": user_turn.raw_text,
            }
        )
        if self.llm_client is None:
            return self._mock_turn_analysis(user_turn), prompt

        try:
            payload, _response = self.llm_client.parse_json(prompt)
            return self._parse_turn_analysis(user_turn, payload), prompt
        except RuntimeError:
            return self._mock_turn_analysis(user_turn), prompt

    def _mock_turn_analysis(self, user_turn: TurnRecord) -> TurnAnalysis:
        argument_id = f"arg-{user_turn.turn_id}-1"
        argument = ArgumentUnit(
            argument_id=argument_id,
            turn_id=user_turn.turn_id,
            speaker_role=SpeakerRole.USER,
            claim=user_turn.normalized_text,
            warrant="用户假定 AI 的重要性可以直接推出强制教育政策。",
            impact="若不强制纳入，学生会失去未来竞争力。",
            argument_type="policy_claim",
            tags=["必要性", "教育政策"],
            strength_score=0.55,
        )
        clash_point = ClashPoint(
            clash_point_id=str(uuid4()),
            topic_label="必要性与可行性",
            summary=f"用户是否证明了从 AI 重要性到强制纳入课程之间的必要性与可行性链条：{user_turn.normalized_text}",
            user_argument_ids=[argument_id],
            open_questions=["为什么必须强制而不是选修推进？", "师资和课时成本由谁承担？"],
            current_pressure_side="opponent",
            last_updated_turn_id=user_turn.turn_id,
        )
        return TurnAnalysis(
            summary=f"用户当前主张：{user_turn.normalized_text}",
            arguments=[argument],
            clash_points=[clash_point],
            pending_response_arguments=[f"尚未证明该结论为何必须通过强制教育实现：{user_turn.normalized_text}"],
            model_notes=["fallback_analysis"],
        )

    def _parse_turn_analysis(self, user_turn: TurnRecord, payload: dict[str, object]) -> TurnAnalysis:
        summary = _ensure_str(payload.get("summary"), default=f"用户当前主张：{user_turn.normalized_text}")
        raw_arguments = payload.get("arguments", [])
        arguments: list[ArgumentUnit] = []
        if isinstance(raw_arguments, list):
            for index, item in enumerate(raw_arguments[:3], start=1):
                if not isinstance(item, dict):
                    continue
                argument_id = f"arg-{user_turn.turn_id}-{index}"
                arguments.append(
                    ArgumentUnit(
                        argument_id=argument_id,
                        turn_id=user_turn.turn_id,
                        speaker_role=SpeakerRole.USER,
                        claim=_ensure_str(item.get("claim"), default=user_turn.normalized_text),
                        warrant=_ensure_str(item.get("warrant")),
                        impact=_ensure_str(item.get("impact")),
                        argument_type=_ensure_str(item.get("argument_type"), default="unspecified"),
                        tags=_ensure_list(item.get("tags")),
                        strength_score=_ensure_float(item.get("strength_score")),
                    )
                )
        if not arguments:
            return self._mock_turn_analysis(user_turn)

        raw_clash_points = payload.get("clash_points", [])
        clash_points: list[ClashPoint] = []
        if isinstance(raw_clash_points, list):
            for item in raw_clash_points[:2]:
                if not isinstance(item, dict):
                    continue
                clash_points.append(
                    ClashPoint(
                        clash_point_id=str(uuid4()),
                        topic_label=_ensure_str(item.get("topic_label"), default="核心交锋点"),
                        summary=_ensure_str(item.get("summary"), default=summary),
                        user_argument_ids=[argument.argument_id for argument in arguments],
                        open_questions=_ensure_list(item.get("open_questions"))[:3],
                        current_pressure_side="opponent",
                        last_updated_turn_id=user_turn.turn_id,
                    )
                )
        if not clash_points:
            clash_points = self._mock_turn_analysis(user_turn).clash_points

        return TurnAnalysis(
            summary=summary,
            arguments=arguments,
            clash_points=clash_points,
            pending_response_arguments=_ensure_list(payload.get("pending_response_arguments")),
            model_notes=_ensure_list(payload.get("model_notes")),
        )


class OpponentAgent:
    def __init__(self, llm_client: DebateLLMClient | None = None, model_name: str | None = None) -> None:
        self.llm_client = llm_client
        self.model_name = model_name

    def generate(
        self,
        session: DebateSession,
        profile: DebateProfile,
        user_text: str,
        recent_turns_summary: str,
        active_clash_points: list[ClashPoint],
        pending_response_arguments: list[str],
        target_argument_ids: list[str],
        evidence_records: list[EvidenceRecord],
    ) -> tuple[AgentOutput, str, str | None]:
        prompt_variables = build_opponent_variables(
            session=session,
            profile=profile,
            recent_turns_summary=recent_turns_summary,
            active_clash_points=active_clash_points,
            pending_response_arguments="；".join(pending_response_arguments),
            target_argument_ids=target_argument_ids,
            evidence_records=evidence_records,
        )
        prompt_variables["latest_user_turn"] = user_text
        prompt = OPPONENT_TEMPLATE.render(prompt_variables)

        if self.llm_client is None:
            return self._mock_opponent_output(user_text, target_argument_ids, evidence_records), prompt, None

        try:
            payload, response = self.llm_client.parse_json(prompt, model=self.model_name)
            return self._parse_opponent_payload(payload, target_argument_ids, evidence_records), prompt, response.model
        except RuntimeError:
            return self._mock_opponent_output(user_text, target_argument_ids, evidence_records), prompt, None

    def _mock_opponent_output(
        self,
        user_text: str,
        target_argument_ids: list[str],
        evidence_records: list[EvidenceRecord],
    ) -> AgentOutput:
        evidence_ids = [item.evidence_id for item in evidence_records]
        return AgentOutput(
            rebuttal_target_ids=target_argument_ids,
            attack_strategy="证明责任攻击",
            response_outline=[
                "把重要性和强制纳入直接等同，论证跳步。",
                "没有证明学校具备统一执行条件。",
                "没有回答课程置换和资源成本问题。",
            ],
            spoken_text=(
                f"你现在的问题不是没有看到 AI 的重要性，而是把‘重要’直接跳成了‘必须强制纳入’。"
                f"这中间至少差了两步证明：第一，你要证明为什么现有课程和选修机制不足；第二，你要证明学校有能力承担统一推进的师资和课时成本。"
                f"如果这些条件都没证明，你的结论就不是政策主张，只是愿景表态。"
            ),
            follow_up_questions=[
                "请你具体说明，为什么这件事必须是强制纳入，而不能是校本或选修推进？",
                "如果新增课程要占用现有课时，你准备牺牲哪一门，依据是什么？",
            ],
            evidence_citations=evidence_ids,
            pressure_score=4,
        )

    def _parse_opponent_payload(
        self,
        payload: dict[str, object],
        fallback_target_ids: list[str],
        evidence_records: list[EvidenceRecord],
    ) -> AgentOutput:
        evidence_ids = {item.evidence_id for item in evidence_records}
        raw_citations = payload.get("evidence_citations", [])
        citations = [item for item in _ensure_list(raw_citations) if item in evidence_ids]
        pressure_score = _ensure_int(payload.get("pressure_score"), default=3, minimum=1, maximum=5)
        return AgentOutput(
            rebuttal_target_ids=_ensure_list(payload.get("rebuttal_target_ids")) or fallback_target_ids,
            attack_strategy=_ensure_str(payload.get("attack_strategy"), default="未说明攻击路径"),
            response_outline=_ensure_list(payload.get("response_outline")),
            spoken_text=_ensure_str(payload.get("spoken_text"), default="未生成正式发言。"),
            follow_up_questions=_ensure_list(payload.get("follow_up_questions")),
            evidence_citations=citations,
            pressure_score=pressure_score,
            self_check_flags=_ensure_list(payload.get("self_check_flags")),
        )


class CoachAgent:
    def __init__(self, llm_client: DebateLLMClient | None = None, model_name: str | None = None) -> None:
        self.llm_client = llm_client
        self.model_name = model_name

    def generate(
        self,
        session: DebateSession,
        profile: DebateProfile,
        recent_turns_summary: str,
        active_clash_points: list[ClashPoint],
        evidence_records: list[EvidenceRecord],
        latest_user_turn: str,
        latest_opponent_turn: str,
        related_turn_ids: list[str],
    ) -> CoachGenerationResult:
        prompt_variables = build_coach_variables(
            session=session,
            profile=profile,
            recent_turns_summary=recent_turns_summary,
            active_clash_points=active_clash_points,
            evidence_records=evidence_records,
            latest_user_turn=latest_user_turn,
            latest_opponent_turn=latest_opponent_turn,
        )
        prompt = COACH_TEMPLATE.render(prompt_variables)
        if self.llm_client is None:
            return CoachGenerationResult(
                coach_report=self._mock_coach_report(session, related_turn_ids),
                prompt=prompt,
                model_name=None,
            )

        try:
            payload, response = self.llm_client.parse_json(prompt, model=self.model_name)
            return CoachGenerationResult(
                coach_report=self._parse_coach_payload(session, payload, related_turn_ids),
                prompt=prompt,
                model_name=response.model,
            )
        except RuntimeError:
            return CoachGenerationResult(
                coach_report=self._mock_coach_report(session, related_turn_ids),
                prompt=prompt,
                model_name=None,
            )

    def _mock_coach_report(self, session: DebateSession, related_turn_ids: list[str]) -> CoachReport:
        return CoachReport(
            report_id=str(uuid4()),
            session_id=session.session_id,
            scope="turn",
            round_verdict="对手暂时占优，因为用户把重要性直接跳成了强制性结论。",
            diagnosed_weaknesses=[
                {
                    "weakness_type": "burden_control",
                    "symptom": "没有证明为什么必须强制纳入课程。",
                    "why_it_hurts": "这让对手可以持续追问必要性和可行性。",
                }
            ],
            missed_responses=["资源和课程置换成本没有回应。"],
            logical_fallacies=["结论跳步"],
            score_card={
                "clash_handling": 2,
                "responsiveness": 2,
                "burden_control": 1,
                "evidence_use": 1,
                "framing": 2,
                "composure": 3,
            },
            improvement_actions=[
                "先证明为什么不能通过选修或校本方式达成目标。",
                "补上资源来源和课时置换的执行路径。",
            ],
            confidence_notes=["当前为规则化 mock 反馈。"],
            related_turn_ids=related_turn_ids,
        )

    def _parse_coach_payload(
        self,
        session: DebateSession,
        payload: dict[str, object],
        related_turn_ids: list[str],
    ) -> CoachReport:
        score_card_input = payload.get("score_card", {})
        score_card = score_card_input if isinstance(score_card_input, dict) else {}
        normalized_score_card = {
            str(key): _ensure_int(value, default=3, minimum=1, maximum=5)
            for key, value in score_card.items()
        }
        raw_weaknesses = payload.get("diagnosed_weaknesses", [])
        weaknesses: list[dict[str, str]] = []
        if isinstance(raw_weaknesses, list):
            for item in raw_weaknesses:
                if isinstance(item, dict):
                    weaknesses.append({str(key): _ensure_str(value) for key, value in item.items()})

        return CoachReport(
            report_id=str(uuid4()),
            session_id=session.session_id,
            scope=_ensure_str(payload.get("scope"), default="turn"),
            round_verdict=_ensure_str(payload.get("round_verdict"), default="未生成回合判断。"),
            diagnosed_weaknesses=weaknesses,
            missed_responses=_ensure_list(payload.get("user_missed_responses")),
            logical_fallacies=_ensure_list(payload.get("logical_fallacies")),
            score_card=normalized_score_card,
            improvement_actions=_ensure_list(payload.get("repair_suggestions")) or _ensure_list(payload.get("next_round_priorities")),
            confidence_notes=_ensure_list(payload.get("confidence_notes")),
            related_turn_ids=related_turn_ids,
        )


class ClosingAgent:
    def __init__(self, llm_client: DebateLLMClient | None = None, model_name: str | None = None) -> None:
        self.llm_client = llm_client
        self.model_name = model_name

    def generate(
        self,
        session: DebateSession,
        profile: DebateProfile,
        recent_turns_summary: str,
        active_clash_points: list[ClashPoint],
        evidence_records: list[EvidenceRecord],
        speaker_side: str,
        closing_focus: str,
    ) -> ClosingGenerationResult:
        prompt_variables = build_closing_variables(
            session=session,
            profile=profile,
            recent_turns_summary=recent_turns_summary,
            active_clash_points=active_clash_points,
            evidence_records=evidence_records,
            speaker_side=speaker_side,
            closing_focus=closing_focus,
        )
        prompt = CLOSING_TEMPLATE.render(prompt_variables)
        if self.llm_client is None:
            return ClosingGenerationResult(
                closing_output=self._mock_closing_output(session, speaker_side, evidence_records),
                prompt=prompt,
                model_name=None,
            )

        try:
            payload, response = self.llm_client.parse_json(prompt, model=self.model_name)
            return ClosingGenerationResult(
                closing_output=self._parse_closing_payload(session, speaker_side, payload, evidence_records),
                prompt=prompt,
                model_name=response.model,
            )
        except RuntimeError:
            return ClosingGenerationResult(
                closing_output=self._mock_closing_output(session, speaker_side, evidence_records),
                prompt=prompt,
                model_name=None,
            )

    def _mock_closing_output(
        self,
        session: DebateSession,
        speaker_side: str,
        evidence_records: list[EvidenceRecord],
    ) -> ClosingOutput:
        evidence_ids = [item.evidence_id for item in evidence_records[:3]]
        evidence_lines = self._build_evidence_lines(evidence_records)
        evidence_paragraph = " ".join(evidence_lines)
        return ClosingOutput(
            closing_id=str(uuid4()),
            session_id=session.session_id,
            speaker_side=speaker_side,
            strategy_summary="先给出裁判标准，再用证据化的赢点与对方未完成的证明责任完成判决收束。",
            outline=[
                "先重述辩题与裁判标准，并说明本方为什么更符合这一标准。",
                "再用资料化的赢点证明本方主张更有现实支撑。",
                "最后点明对方没有补上的证明责任，并回到辩题完成判决。",
            ],
            spoken_text=(
                f"各位评判，这场辩论的题目不是要不要承认 AI 很重要，而是 {session.topic}。"
                f"所以真正的判断标准只有一个：哪一方更完整地证明了自己的立场在必要性、可行性和净收益上成立。"
                f"如果一项主张要走向制度化、走向普遍实施，它就必须拿出足够的现实依据和执行论证，而不能只停留在目标正确。"
                f"{evidence_paragraph}"
                f"也正因为如此，我们今天的赢点非常清楚。第一，我们始终把比赛拉回到辩题要求的证明责任上。"
                f"对方不断强调 AI 教育的重要性，但重要性本身并不能自动推出强制性制度安排。"
                f"第二，我们证明了这类政策主张真正会被追问的，不是愿景，而是执行路径、资源承载和替代方案比较。"
                f"如果这些关键问题没有回答，那么对方给出的就不是成熟政策，而只是价值表态。"
                f"第三，在现有交锋里，对方始终没有补上为什么必须强制、为什么不能通过选修或校本推进、以及为什么学校系统已经准备好的论证。"
                f"这意味着他们没有越过政策辩论最基本的门槛。"
                f"所以请各位评判回到辩题本身来看：谁真正证明了自己的立场更符合判断标准？"
                f"答案不是更会描绘未来的人，而是更能完成证明责任的人。"
                f"在这个标准下，对方的论证仍然停留在口号阶段，而我们已经指出了它在必要性与可行性上的核心断裂。"
                f"因此，这道题应当判给 {speaker_side}。"
            ),
            evidence_citations=evidence_ids,
            confidence_notes=["当前为 fallback 陈词稿，可继续人工打磨语气和段落。"],
        )

    def _build_evidence_lines(self, evidence_records: list[EvidenceRecord]) -> list[str]:
        lines: list[str] = []
        ranked_records = sorted(
            evidence_records,
            key=lambda item: (
                item.credibility_score if item.credibility_score is not None else 0.0,
                item.relevance_score if item.relevance_score is not None else 0.0,
            ),
            reverse=True,
        )
        for evidence in ranked_records[:2]:
            source_name = evidence.title or evidence.source_ref
            if (evidence.credibility_score or 0.0) >= 0.8:
                lines.append(f"就连较高可信度的外部资料都在提醒我们，{source_name}指出：{evidence.snippet}。")
                continue
            if "research" in evidence.source_type or "study" in evidence.title.lower() or "研究" in evidence.title:
                lines.append(f"已有研究路径支持这一点，{source_name}的核心结论是：{evidence.snippet}。")
                continue
            lines.append(f"从现有可核查资料看，{source_name}至少提示了这样一个现实倾向：{evidence.snippet}。")
        if not lines:
            lines.append("即便暂时拿不到足够硬的数据，单从制度论证逻辑也能看出，对方没有完成从价值目标到制度结论之间的证明闭环。")
            lines.append("设想一个最普通的现实场景：当执行条件、资源承载和替代方案都还没有论清时，任何强制性主张都会先把成本和风险压到真实使用者身上。")
        return lines

    def _parse_closing_payload(
        self,
        session: DebateSession,
        speaker_side: str,
        payload: dict[str, object],
        evidence_records: list[EvidenceRecord],
    ) -> ClosingOutput:
        evidence_ids = {item.evidence_id for item in evidence_records}
        citations = [item for item in _ensure_list(payload.get("evidence_citations")) if item in evidence_ids]
        return ClosingOutput(
            closing_id=str(uuid4()),
            session_id=session.session_id,
            speaker_side=speaker_side,
            strategy_summary=_ensure_str(payload.get("strategy_summary"), default="未提供陈词策略摘要。"),
            outline=_ensure_list(payload.get("outline")),
            spoken_text=_ensure_str(payload.get("spoken_text"), default="未生成正式陈词稿。"),
            evidence_citations=citations,
            confidence_notes=_ensure_list(payload.get("confidence_notes")),
        )


class OpeningAgent:
    def __init__(self, llm_client: DebateLLMClient | None = None, model_name: str | None = None) -> None:
        self.llm_client = llm_client
        self.model_name = model_name

    def generate(
        self,
        session: DebateSession,
        profile: DebateProfile,
        evidence_records: list[EvidenceRecord],
        speaker_side: str,
        brief_focus: str,
        target_duration_minutes: int,
        progress_callback: Callable[[dict[str, object]], None] | None = None,
    ) -> OpeningGenerationResult:
        framework_result = self.generate_framework(
            session=session,
            profile=profile,
            evidence_records=evidence_records,
            speaker_side=speaker_side,
            brief_focus=brief_focus,
            progress_callback=progress_callback,
        )
        draft_result = self.generate_from_framework(
            session=session,
            profile=profile,
            speaker_side=speaker_side,
            brief_focus=brief_focus,
            framework=framework_result.framework,
            target_duration_minutes=target_duration_minutes,
            progress_callback=progress_callback,
        )
        return OpeningGenerationResult(
            opening_brief=draft_result.opening_brief,
            prompt=f"{framework_result.prompt}\n\n-----\n\n{draft_result.prompt}",
            model_name=draft_result.model_name or framework_result.model_name,
        )

    def generate_framework(
        self,
        session: DebateSession,
        profile: DebateProfile,
        evidence_records: list[EvidenceRecord],
        speaker_side: str,
        brief_focus: str,
        progress_callback: Callable[[dict[str, object]], None] | None = None,
    ) -> OpeningFrameworkGenerationResult:
        if progress_callback is not None:
            progress_callback(
                {
                    "event": "stage",
                    "stage": "framework_started",
                    "message": "正在生成独立框架稿。",
                }
            )
        framework_prompt_variables = build_opening_variables(
            session=session,
            profile=profile,
            evidence_records=evidence_records,
            speaker_side=speaker_side,
            brief_focus=brief_focus,
            target_duration_minutes=3,
        )
        framework_base_prompt = OPENING_FRAMEWORK_TEMPLATE.render(framework_prompt_variables)
        if self.llm_client is None:
            framework = self._build_mock_framework(session=session, profile=profile, evidence_records=evidence_records)
            self._emit_framework_ready(progress_callback, framework, "已使用内置框架稿。")
            return OpeningFrameworkGenerationResult(framework=framework, prompt=framework_base_prompt, model_name=None)

        last_model_name: str | None = None
        framework_prompt = framework_base_prompt
        framework: OpeningFramework | None = None
        framework_errors: list[str] = []
        for attempt in range(3):
            try:
                payload, response = self.llm_client.parse_json(framework_prompt, model=self.model_name)
                last_model_name = response.model
            except RuntimeError as error:
                if attempt == 2:
                    break
                framework_prompt = self._build_framework_retry_prompt(
                    framework_base_prompt,
                    [f"第 {attempt + 1} 次框架稿生成失败：{error}"],
                    None,
                )
                continue

            framework = self._parse_opening_framework(payload, profile)
            framework_errors = self._validate_opening_framework(framework, session, profile)
            if not framework_errors:
                self._emit_framework_ready(progress_callback, framework, "框架稿已生成。")
                return OpeningFrameworkGenerationResult(framework=framework, prompt=framework_prompt, model_name=last_model_name)
            if attempt == 2:
                break
            framework_prompt = self._build_framework_retry_prompt(framework_base_prompt, framework_errors, framework)

        framework = self._build_mock_framework(session=session, profile=profile, evidence_records=evidence_records)
        if progress_callback is not None:
            progress_callback(
                {
                    "event": "stage",
                    "stage": "fallback_started",
                    "message": "模型框架稿不稳定，正在回退到内置框架生成。",
                }
            )
        self._emit_framework_ready(progress_callback, framework, "已回退到内置框架稿。")
        return OpeningFrameworkGenerationResult(framework=framework, prompt=framework_prompt, model_name=last_model_name)

    def generate_from_framework(
        self,
        session: DebateSession,
        profile: DebateProfile,
        speaker_side: str,
        brief_focus: str,
        framework: OpeningFramework,
        target_duration_minutes: int,
        progress_callback: Callable[[dict[str, object]], None] | None = None,
    ) -> OpeningGenerationResult:
        target_duration_minutes = max(1, min(target_duration_minutes, 8))
        if self.llm_client is None:
            fallback_brief = self._mock_opening_brief_from_framework(session, speaker_side, framework, target_duration_minutes)
            if progress_callback is not None:
                progress_callback(
                    {
                        "event": "stage",
                        "stage": "draft_started",
                        "message": f"正在把当前框架稿写成 {target_duration_minutes} 分钟正式成稿。",
                    }
                )
            return OpeningGenerationResult(
                opening_brief=fallback_brief,
                prompt=OPENING_DRAFT_TEMPLATE.render(
                    build_opening_draft_variables(
                        session=session,
                        profile=profile,
                        speaker_side=speaker_side,
                        brief_focus=brief_focus,
                        target_duration_minutes=target_duration_minutes,
                        framework=framework,
                    )
                ),
                model_name=None,
            )

        last_model_name: str | None = None
        if progress_callback is not None:
            progress_callback(
                {
                    "event": "stage",
                    "stage": "draft_started",
                    "message": f"正在把当前框架稿写成 {target_duration_minutes} 分钟正式成稿。",
                }
            )

        draft_prompt_variables = build_opening_draft_variables(
            session=session,
            profile=profile,
            speaker_side=speaker_side,
            brief_focus=brief_focus,
            target_duration_minutes=target_duration_minutes,
            framework=framework,
        )
        draft_base_prompt = OPENING_DRAFT_TEMPLATE.render(draft_prompt_variables)
        draft_prompt = draft_base_prompt
        if progress_callback is not None:
            progress_callback(
                {
                    "event": "stage",
                    "stage": "draft_started",
                    "message": f"正在把框架稿写成 {target_duration_minutes} 分钟正式成稿。",
                }
            )
        for attempt in range(3):
            try:
                payload, response = self.llm_client.parse_json(draft_prompt, model=self.model_name)
                last_model_name = response.model
            except RuntimeError as error:
                if attempt == 2:
                    break
                draft_prompt = self._build_draft_retry_prompt(
                    draft_base_prompt,
                    [f"第 {attempt + 1} 次成稿生成失败：{error}"],
                    None,
                )
                continue

            opening_brief = self._parse_opening_payload(
                session=session,
                speaker_side=speaker_side,
                payload=payload,
                framework=framework,
                target_duration_minutes=target_duration_minutes,
            )
            validation_errors = self._validate_opening_brief(opening_brief)
            if not validation_errors:
                return OpeningGenerationResult(
                    opening_brief=opening_brief,
                    prompt=draft_prompt,
                    model_name=last_model_name,
                )
            if attempt == 2:
                break
            draft_prompt = self._build_draft_retry_prompt(draft_base_prompt, validation_errors, opening_brief)

        return OpeningGenerationResult(
            opening_brief=self._mock_opening_brief_from_framework(session, speaker_side, framework, target_duration_minutes),
            prompt=draft_prompt,
            model_name=last_model_name,
        )

    def generate_stream(
        self,
        session: DebateSession,
        profile: DebateProfile,
        evidence_records: list[EvidenceRecord],
        speaker_side: str,
        brief_focus: str,
        target_duration_minutes: int,
        progress_callback: Callable[[dict[str, object]], None] | None = None,
    ) -> OpeningGenerationResult:
        framework_result = self.generate_framework(
            session=session,
            profile=profile,
            evidence_records=evidence_records,
            speaker_side=speaker_side,
            brief_focus=brief_focus,
            progress_callback=progress_callback,
        )
        draft_result = self.generate_stream_from_framework(
            session=session,
            profile=profile,
            speaker_side=speaker_side,
            brief_focus=brief_focus,
            framework=framework_result.framework,
            target_duration_minutes=target_duration_minutes,
            progress_callback=progress_callback,
        )
        return OpeningGenerationResult(
            opening_brief=draft_result.opening_brief,
            prompt=f"{framework_result.prompt}\n\n-----\n\n{draft_result.prompt}",
            model_name=draft_result.model_name or framework_result.model_name,
        )

    def generate_stream_from_framework(
        self,
        session: DebateSession,
        profile: DebateProfile,
        speaker_side: str,
        brief_focus: str,
        framework: OpeningFramework,
        target_duration_minutes: int,
        progress_callback: Callable[[dict[str, object]], None] | None = None,
    ) -> OpeningGenerationResult:
        target_duration_minutes = max(1, min(target_duration_minutes, 8))
        if self.llm_client is None:
            fallback_brief = self._mock_opening_brief_from_framework(session, speaker_side, framework, target_duration_minutes)
            if progress_callback is not None:
                progress_callback(
                    {
                        "event": "stage",
                        "stage": "draft_started",
                        "message": f"正在把当前框架稿写成 {target_duration_minutes} 分钟正式成稿。",
                    }
                )
            self._stream_text(progress_callback, fallback_brief.spoken_text)
            return OpeningGenerationResult(
                opening_brief=fallback_brief,
                prompt=OPENING_DRAFT_STREAM_TEMPLATE.render(
                    build_opening_draft_variables(
                        session=session,
                        profile=profile,
                        speaker_side=speaker_side,
                        brief_focus=brief_focus,
                        target_duration_minutes=target_duration_minutes,
                        framework=framework,
                    )
                ),
                model_name=None,
            )

        last_model_name: str | None = None
        draft_prompt_variables = build_opening_draft_variables(
            session=session,
            profile=profile,
            speaker_side=speaker_side,
            brief_focus=brief_focus,
            target_duration_minutes=target_duration_minutes,
            framework=framework,
        )
        draft_base_prompt = OPENING_DRAFT_STREAM_TEMPLATE.render(draft_prompt_variables)
        draft_prompt = draft_base_prompt
        if progress_callback is not None:
            progress_callback(
                {
                    "event": "stage",
                    "stage": "draft_started",
                    "message": f"正在把框架稿写成 {target_duration_minutes} 分钟正式成稿。",
                }
            )

        for attempt in range(3):
            streamed_chunks: list[str] = []
            try:
                for chunk in self.llm_client.generate_text_stream(draft_prompt, model=self.model_name):
                    streamed_chunks.append(chunk)
                    if progress_callback is not None:
                        progress_callback({"event": "opening_chunk", "chunk": chunk})
            except RuntimeError as error:
                if attempt == 2:
                    break
                if progress_callback is not None:
                    progress_callback({"event": "opening_reset", "message": "流式写稿中断，正在自动重试。"})
                draft_prompt = self._build_stream_draft_retry_prompt(
                    draft_base_prompt,
                    [f"第 {attempt + 1} 次成稿流式生成失败：{error}"],
                    "".join(streamed_chunks),
                )
                continue

            opening_brief = self._build_stream_opening_brief(
                session=session,
                speaker_side=speaker_side,
                spoken_text="".join(streamed_chunks),
                framework=framework,
                target_duration_minutes=target_duration_minutes,
            )
            validation_errors = self._validate_opening_brief(opening_brief)
            if not validation_errors:
                return OpeningGenerationResult(
                    opening_brief=opening_brief,
                    prompt=draft_prompt,
                    model_name=last_model_name,
                )
            if attempt == 2:
                break
            if progress_callback is not None:
                progress_callback({"event": "opening_reset", "message": "当前成稿未通过校验，正在自动重写。"})
            draft_prompt = self._build_stream_draft_retry_prompt(
                draft_base_prompt,
                validation_errors,
                opening_brief.spoken_text,
            )

        fallback_brief = self._mock_opening_brief_from_framework(session, speaker_side, framework, target_duration_minutes)
        if progress_callback is not None:
            progress_callback({"event": "opening_reset", "message": "流式成稿不稳定，已回退到内置一辩稿。"})
            progress_callback(
                {
                    "event": "stage",
                    "stage": "fallback_started",
                    "message": "正在下发回退稿件。",
                }
            )
        self._stream_text(progress_callback, fallback_brief.spoken_text)
        return OpeningGenerationResult(
            opening_brief=fallback_brief,
            prompt=draft_prompt,
            model_name=last_model_name,
        )

    def _mock_opening_brief(
        self,
        session: DebateSession,
        profile: DebateProfile,
        speaker_side: str,
        evidence_records: list[EvidenceRecord],
        target_duration_minutes: int,
    ) -> OpeningBrief:
        target_word_count = target_duration_minutes * 300
        framework = self._build_mock_framework(session=session, profile=profile, evidence_records=evidence_records)
        evidence_ids = [item.evidence_id for item in evidence_records[:3]]
        return OpeningBrief(
            brief_id=str(uuid4()),
            session_id=session.session_id,
            speaker_side=speaker_side,
            strategy_summary="先定判断标准，再用 2 到 3 个核心论点承接数据、学理、情景三类填充，最后压回证明责任。",
            outline=[self._summarize_argument_claim(card.claim, index) for index, card in enumerate(framework.argument_cards, start=1)],
            spoken_text=self._compose_fallback_draft(session, speaker_side, framework, target_duration_minutes),
            evidence_citations=evidence_ids,
            confidence_notes=["当前为 fallback 一辩稿，已先构建框架稿，再按目标时长生成成稿。"],
            source_mode="generated",
            framework=framework,
            target_duration_minutes=target_duration_minutes,
            target_word_count=target_word_count,
        )

    def _mock_opening_brief_from_framework(
        self,
        session: DebateSession,
        speaker_side: str,
        framework: OpeningFramework,
        target_duration_minutes: int,
    ) -> OpeningBrief:
        target_word_count = target_duration_minutes * 300
        return OpeningBrief(
            brief_id=str(uuid4()),
            session_id=session.session_id,
            speaker_side=speaker_side,
            strategy_summary=framework.framework_summary or "基于当前框架稿扩写正式一辩稿。",
            outline=[self._summarize_argument_claim(card.claim, index) for index, card in enumerate(framework.argument_cards, start=1)],
            spoken_text=self._compose_fallback_draft(session, speaker_side, framework, target_duration_minutes),
            evidence_citations=[],
            confidence_notes=["当前为 fallback 一辩稿，严格基于现有框架稿扩写。"],
            source_mode="generated",
            framework=framework,
            target_duration_minutes=target_duration_minutes,
            target_word_count=target_word_count,
        )

    def _parse_opening_framework(self, payload: dict[str, object], profile: DebateProfile) -> OpeningFramework:
        raw_cards = payload.get("argument_cards", [])
        cards: list[OpeningArgumentCard] = []
        if isinstance(raw_cards, list):
            for item in raw_cards[:3]:
                if not isinstance(item, dict):
                    continue
                cards.append(
                    OpeningArgumentCard(
                        claim=_ensure_str(item.get("claim")),
                        data_support=_ensure_str(item.get("data_support")),
                        academic_support=_ensure_str(item.get("academic_support")),
                        scenario_support=_ensure_str(item.get("scenario_support")),
                    )
                )
        return OpeningFramework(
            judge_standard=_ensure_str(payload.get("judge_standard"), default=profile.judge_standard),
            framework_summary=_ensure_str(payload.get("framework_summary"), default="未提供框架摘要。"),
            argument_cards=cards,
        )

    def _parse_opening_payload(
        self,
        session: DebateSession,
        speaker_side: str,
        payload: dict[str, object],
        framework: OpeningFramework,
        target_duration_minutes: int,
    ) -> OpeningBrief:
        return OpeningBrief(
            brief_id=str(uuid4()),
            session_id=session.session_id,
            speaker_side=speaker_side,
            strategy_summary=_ensure_str(payload.get("strategy_summary"), default="未提供一辩稿策略摘要。"),
            outline=_ensure_list(payload.get("outline")) or [self._summarize_argument_claim(card.claim, index) for index, card in enumerate(framework.argument_cards, start=1)],
            spoken_text=_ensure_str(payload.get("spoken_text"), default="未生成一辩稿正文。"),
            evidence_citations=[],
            confidence_notes=_ensure_list(payload.get("confidence_notes")),
            source_mode="generated",
            framework=framework,
            target_duration_minutes=target_duration_minutes,
            target_word_count=target_duration_minutes * 300,
        )

    def _build_stream_opening_brief(
        self,
        session: DebateSession,
        speaker_side: str,
        spoken_text: str,
        framework: OpeningFramework,
        target_duration_minutes: int,
    ) -> OpeningBrief:
        return OpeningBrief(
            brief_id=str(uuid4()),
            session_id=session.session_id,
            speaker_side=speaker_side,
            strategy_summary=framework.framework_summary or "基于框架稿展开正式一辩稿。",
            outline=[self._summarize_argument_claim(card.claim, index) for index, card in enumerate(framework.argument_cards, start=1)],
            spoken_text=spoken_text.strip(),
            evidence_citations=[],
            confidence_notes=["当前为后端流式生成的一辩稿。"],
            source_mode="generated",
            framework=framework,
            target_duration_minutes=target_duration_minutes,
            target_word_count=target_duration_minutes * 300,
        )

    def _build_framework_retry_prompt(self, base_prompt: str, validation_errors: list[str], framework: OpeningFramework | None) -> str:
        previous_output = framework.framework_summary if framework is not None else "上一次没有得到可用框架稿。"
        issues = "\n".join(f"- {item}" for item in validation_errors)
        return (
            f"{base_prompt}\n\n"
            "[Retry Instruction]\n"
            "你上一版框架稿未通过结构校验，请严格重写，不要在原稿上轻微修补。\n"
            "未通过原因：\n"
            f"{issues}\n\n"
            "你必须重新输出 JSON，并确保 judge_standard、framework_summary 和 2 到 3 个 argument_cards 齐全。\n"
            "每个 argument_card 都必须补齐 data_support、academic_support、scenario_support。\n"
            "以下是上一版不合格框架摘要，仅供你识别问题，不得照抄：\n"
            f"{previous_output}"
        )

    def _build_draft_retry_prompt(self, base_prompt: str, validation_errors: list[str], opening_brief: OpeningBrief | None) -> str:
        previous_output = opening_brief.spoken_text if opening_brief is not None else "上一次没有得到可用成稿。"
        issues = "\n".join(f"- {item}" for item in validation_errors)
        return (
            f"{base_prompt}\n\n"
            "[Retry Instruction]\n"
            "你上一版成稿未通过校验，请严格重写，不要在原稿上轻微修补。\n"
            "未通过原因：\n"
            f"{issues}\n\n"
            "你必须继续忠实使用框架稿，并写成完整自然的朗读稿。\n"
            "以下是上一版不合格正文，仅供你识别问题，不得照抄：\n"
            f"{previous_output}"
        )

    def _build_stream_draft_retry_prompt(self, base_prompt: str, validation_errors: list[str], previous_output: str | None) -> str:
        issues = "\n".join(f"- {item}" for item in validation_errors)
        return (
            f"{base_prompt}\n\n"
            "[Retry Instruction]\n"
            "你上一版流式成稿未通过校验，请从头重写，不要延续刚才的表述。\n"
            "未通过原因：\n"
            f"{issues}\n\n"
            "你必须继续忠实使用框架稿，并直接输出完整自然的朗读稿正文。\n"
            "以下是上一版不合格正文，仅供你识别问题，不得照抄：\n"
            f"{previous_output or '上一次没有得到可用正文。'}"
        )

    def _emit_framework_ready(
        self,
        progress_callback: Callable[[dict[str, object]], None] | None,
        framework: OpeningFramework | None,
        message: str,
    ) -> None:
        if progress_callback is None:
            return
        progress_callback(
            {
                "event": "framework_ready",
                "message": message,
                "framework": {
                    "judge_standard": framework.judge_standard if framework is not None else "",
                    "framework_summary": framework.framework_summary if framework is not None else "",
                    "argument_cards": [
                        {
                            "claim": card.claim,
                            "data_support": card.data_support,
                            "academic_support": card.academic_support,
                            "scenario_support": card.scenario_support,
                        }
                        for card in (framework.argument_cards if framework is not None else [])
                    ],
                },
            }
        )

    def _stream_text(
        self,
        progress_callback: Callable[[dict[str, object]], None] | None,
        spoken_text: str,
        chunk_size: int = 48,
        pause_seconds: float = 0.02,
    ) -> None:
        if progress_callback is None:
            return
        for start in range(0, len(spoken_text), chunk_size):
            progress_callback(
                {
                    "event": "opening_chunk",
                    "chunk": spoken_text[start : start + chunk_size],
                }
            )
            if pause_seconds > 0:
                time.sleep(pause_seconds)

    def _validate_opening_framework(self, framework: OpeningFramework, session: DebateSession, profile: DebateProfile) -> list[str]:
        errors: list[str] = []
        if len(framework.judge_standard.strip()) < 18:
            errors.append("判断标准过短，没有说清本方如何证明持方成立。")
        if not self._is_topic_specific_judge_standard(framework.judge_standard, session.topic, profile.judge_standard):
            errors.append("判断标准仍然是宏观泛标准，没有根据当前辩题具体推导。")
        if len(framework.argument_cards) < 2:
            errors.append("核心论点少于 2 个，不足以支撑完整框架稿。")
        _meta_argument_keywords = ["判断标准", "裁判依据", "裁判标准", "评判标准", "为什么判", "如何判断", "本题应该怎么判", "先证明为什么", "建立标准", "确立标准", "先确立"]
        for index, card in enumerate(framework.argument_cards, start=1):
            claim = card.claim or ""
            if any(kw in claim for kw in _meta_argument_keywords):
                errors.append(
                    f"第 {index} 个论点内容仍在讨论如何判断本题，而不是实质内容论证。"
                    "判断标准应写在 judge_standard 字段，argument_cards 只应包含从判断标准导出的内容论证。"
                )
            if len(card.claim.strip()) < 12:
                errors.append(f"第 {index} 个论点主张过短。")
            if len(card.data_support.strip()) < 10:
                errors.append(f"第 {index} 个论点缺少数据填充。")
            if len(card.academic_support.strip()) < 12:
                errors.append(f"第 {index} 个论点缺少学理填充。")
            if len(card.scenario_support.strip()) < 12:
                errors.append(f"第 {index} 个论点缺少情景填充。")
        return errors

    def _validate_opening_brief(self, opening_brief: OpeningBrief) -> list[str]:
        errors: list[str] = []
        text = opening_brief.spoken_text.strip()
        minimum_length = max(420, int(opening_brief.target_word_count * 0.55))
        if len(text) < minimum_length:
            errors.append("正文过短，没有达到目标时长应有的展开密度。")
        if opening_brief.framework is None or len(opening_brief.framework.argument_cards) < 2:
            errors.append("缺少可支撑成稿的框架稿。")
        if not any(keyword in text for keyword in ["判断标准", "证明责任", "评判", "标准"]):
            errors.append("成稿没有把比赛锁回判断标准或证明责任。")
        if not any(keyword in text for keyword in ["机制", "因为", "因此", "意味着", "链条", "所以"]):
            errors.append("成稿没有把论点背后的机制讲清楚。")
        if not any(keyword in text for keyword in ["试想", "场景", "学生", "家庭", "普通人", "现实"]):
            errors.append("成稿没有呈现足够具体的现实场景。")
        return errors

    def _build_mock_framework(self, session: DebateSession, profile: DebateProfile, evidence_records: list[EvidenceRecord]) -> OpeningFramework:
        evidence_text = self._summarize_evidence_for_framework(evidence_records)
        topic_judge_standard = self._infer_topic_specific_judge_standard(session.topic, profile)
        return OpeningFramework(
            judge_standard=topic_judge_standard,
            framework_summary=f"本方先用本题专属判断标准锁定比赛，再用 2 到 3 个核心论点证明 {session.topic} 下本方路径更成立。",
            argument_cards=[
                OpeningArgumentCard(
                    claim="本方的第一层优势，是这条路径能直接改善本题最核心的结果指标，而不是停留在抽象愿景。",
                    data_support=evidence_text,
                    academic_support="学理上，判断一项制度主张是否成立，关键不在目标是否美好，而在它能否稳定地把目标转化为现实结果。",
                    scenario_support="放进真实生活里看，真正影响个体处境的不是口号，而是这套安排能不能持续改变他们面对问题时的真实结果。",
                ),
                OpeningArgumentCard(
                    claim="本方的核心优势在于把价值目标通向现实结果的机制链条讲清楚。",
                    data_support=evidence_text,
                    academic_support="机制层面上，当资源、信息和执行条件不能稳定配置时，最终结果往往不是均衡受益，而是差距继续扩大。",
                    scenario_support="试想两个起点接近的人，一个得到稳定配置，一个只能自己零散摸索，差距最终会在真实成本和机会获取上被拉开。",
                ),
                OpeningArgumentCard(
                    claim="对方如果要反驳本方，就必须回答他们如何在没有本方路径的情况下达成同样结果。",
                    data_support="即便暂时缺少足够硬数据，这一步也要求对方拿出替代路径的现实支撑，而不是空谈可能性。",
                    academic_support="比较论证的关键不只是挑本方毛病，而是证明替代方案同样可行且成本更低。",
                    scenario_support="一旦进入真实决策场景，无法说明谁来执行、谁承担成本、谁真正受益的方案，最终都很难被采信。",
                ),
            ],
        )

    def _is_topic_specific_judge_standard(self, judge_standard: str, topic: str, profile_judge_standard: str) -> bool:
        normalized_standard = "".join(judge_standard.lower().split())
        normalized_profile = "".join(profile_judge_standard.lower().split())
        if not normalized_standard or normalized_standard == normalized_profile:
            return False

        topic_keywords = [
            keyword for keyword in re.findall(r"[\u4e00-\u9fffA-Za-z]{2,}", topic) if keyword not in {"是否", "应当", "应该", "可以", "我们"}
        ]
        if any(keyword.lower() in normalized_standard for keyword in topic_keywords[:6]):
            return True

        specificity_keywords = ["未成年人", "教育", "公平", "平台", "治理", "权利", "自由", "资源", "副作用", "误伤", "比例", "执行"]
        return any(keyword.lower() in normalized_standard for keyword in specificity_keywords)

    def _infer_topic_specific_judge_standard(self, topic: str, profile: DebateProfile) -> str:
        if any(keyword in topic for keyword in ["记忆", "失忆", "人格", "责任", "罪行", "罪责", "刑罚", "谴责", "自责", "法律"]):
            return "比较哪一方更能证明其责任归属方案在主体连续性、规范正当性与社会后果上整体更成立。"
        if any(keyword in topic for keyword in ["汽车", "新能源", "整车", "零部件", "芯片", "电机", "产业链", "制造业", "供应链"]):
            return "比较哪一方更能识别并解决当前产业发展的关键约束，在价值链位置、核心能力与长期韧性上形成更优路径。"
        if any(keyword in topic for keyword in ["教育", "学校", "课程", "高中", "大学", "学生"]):
            return "比较哪一方更能证明这项教育安排能在不造成过高资源挤压的前提下，稳定提升目标能力，并改善而非恶化教育公平。"
        if any(keyword in topic for keyword in ["未成年人", "儿童", "青少年"]):
            return "比较哪一方更能在保护未成年人核心利益的同时，以更低误伤、更清晰边界和更可执行的方式完成治理目标。"
        if any(keyword in topic for keyword in ["平台", "监管", "限制", "治理", "封禁", "审查"]):
            return "比较哪一方更能证明其治理手段对核心问题更精准有效、执行边界更清晰、治理副作用和误伤更小。"
        if any(keyword in topic for keyword in ["自由", "权利", "隐私", "表达", "言论", "自主"]):
            return "比较哪一方更能证明自己的立场既实现必要公共目标，又对个人权利施加更少且更可被正当化的限制。"
        if any(keyword in topic for keyword in ["市场", "企业", "经济", "就业", "产业", "效率"]):
            return "比较哪一方更能证明其路径在激励结构、运行效率与长期经济后果上更优，而不是只带来短期表面收益。"
        if profile.debate_type.value == "value":
            return "比较哪一方更能证明自己保护了这道题中更优先的价值，并且为此付出的代价更小。"
        if profile.debate_type.value == "fact":
            return "比较哪一方对这道题的事实判断拥有更强证据质量、更高解释力和更少无法回应的反例。"
        return "比较哪一方更能证明其具体路径在这道题下更必要、更可执行，且整体后果更优。"

    def _summarize_evidence_for_framework(self, evidence_records: list[EvidenceRecord]) -> str:
        if not evidence_records:
            return "当前缺少可直接上场的硬证据，因此这里如实承认数据缺口，再转入学理和情景补位。"
        ranked_records = sorted(
            evidence_records,
            key=lambda item: (
                item.credibility_score if item.credibility_score is not None else 0.0,
                item.relevance_score if item.relevance_score is not None else 0.0,
            ),
            reverse=True,
        )
        selected = ranked_records[:2]
        return "；".join(f"{item.title}指出：{item.snippet}" for item in selected)

    def _compose_fallback_draft(
        self,
        session: DebateSession,
        speaker_side: str,
        framework: OpeningFramework,
        target_duration_minutes: int,
    ) -> str:
        paragraphs = [
            f"各位评判，今天这道题我们不该看哪一方更会描绘愿景，而该看哪一方更能完成证明责任。对本方而言，判断标准非常清楚：{framework.judge_standard}",
            f"先看本方的整体胜利路径。{framework.framework_summary}",
        ]
        for index, card in enumerate(framework.argument_cards, start=1):
            paragraphs.append(
                f"第{index}点，{card.claim}从材料上看，{card.data_support}从机制上看，{card.academic_support}放进真实生活里，{card.scenario_support}"
            )
        paragraphs.append(
            f"所以本方今天的立论并不是几句态度，而是一套完整路径：先定标准，再立论点，再把数据、学理和情景全部压进论证。"
            f"对方如果要反驳 {speaker_side}，就不能只说本方想得太理想，而必须正面回答他们凭什么在没有这套路径的情况下，依然能完成同样的证明责任。"
        )
        text = "".join(paragraphs)
        minimum_length = max(420, int(target_duration_minutes * 300 * 0.72))
        while len(text) < minimum_length:
            text += (
                "回到辩题本身，评判真正要看的不是口号是否动听，而是谁把标准、论点、材料和现实后果连成了一条完整链条。"
                "只要这条链条在本方手里更完整，对方就没有理由仅靠质疑愿景来翻盘。"
            )
        return text

    def _summarize_argument_claim(self, claim: str, index: int) -> str:
        trimmed = claim.strip()
        if not trimmed:
            return f"论点 {index}"
        return trimmed[:18] + ("..." if len(trimmed) > 18 else "")


class OpeningCoachAgent:
    def __init__(self, llm_client: DebateLLMClient | None = None, model_name: str | None = None) -> None:
        self.llm_client = llm_client
        self.model_name = model_name

    def generate(
        self,
        session: DebateSession,
        profile: DebateProfile,
        evidence_records: list[EvidenceRecord],
        opening_brief: OpeningBrief,
    ) -> CoachGenerationResult:
        prompt_variables = build_opening_coach_variables(
            session=session,
            profile=profile,
            evidence_records=evidence_records,
            opening_brief=opening_brief,
        )
        prompt = OPENING_COACH_TEMPLATE.render(prompt_variables)
        related_turn_ids = [opening_brief.brief_id]
        if self.llm_client is None:
            return CoachGenerationResult(
                coach_report=self._mock_opening_coach_report(session, related_turn_ids),
                prompt=prompt,
                model_name=None,
            )

        try:
            payload, response = self.llm_client.parse_json(prompt, model=self.model_name)
            parser = CoachAgent()
            return CoachGenerationResult(
                coach_report=parser._parse_coach_payload(session, payload, related_turn_ids),
                prompt=prompt,
                model_name=response.model,
            )
        except RuntimeError:
            return CoachGenerationResult(
                coach_report=self._mock_opening_coach_report(session, related_turn_ids),
                prompt=prompt,
                model_name=None,
            )

    def _mock_opening_coach_report(self, session: DebateSession, related_turn_ids: list[str]) -> CoachReport:
        return CoachReport(
            report_id=str(uuid4()),
            session_id=session.session_id,
            scope="opening_brief",
            round_verdict="这版一辩稿已经有骨架，但判断标准与后续追问点还可以再压实。",
            diagnosed_weaknesses=[
                {
                    "weakness_type": "framing",
                    "symptom": "判断标准虽然出现了，但还不够早、不够硬。",
                    "why_it_hurts": "这会让后续交锋容易被对方拖去谈抽象价值。",
                }
            ],
            missed_responses=[],
            logical_fallacies=["预埋证明责任不够明确"],
            score_card={
                "clash_handling": 3,
                "responsiveness": 3,
                "burden_control": 4,
                "evidence_use": 3,
                "framing": 3,
                "composure": 4,
            },
            improvement_actions=[
                "把判断标准提前到开篇前两句内讲清。",
                "在每个核心论点结尾补一句‘因此对方必须回答什么’。",
            ],
            confidence_notes=["当前为 fallback 一辩稿教练反馈。"],
            related_turn_ids=related_turn_ids,
        )


def _ensure_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [_ensure_str(item) for item in value if _ensure_str(item)]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _ensure_str(value: object, default: str = "") -> str:
    if isinstance(value, str):
        return value.strip()
    if value is None:
        return default
    return str(value).strip() or default


def _ensure_int(value: object, default: int, minimum: int, maximum: int) -> int:
    try:
        numeric = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        numeric = default
    return max(minimum, min(maximum, numeric))


def _ensure_float(value: object) -> float | None:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None