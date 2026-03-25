from __future__ import annotations

import json
from queue import Empty, Queue
from pathlib import Path
from threading import Thread
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from debate_agent.app.service import DebateApplication, NewSessionRequest
from debate_agent.domain.models import CoachFeedbackMode, DebatePhase, DebateProfile, DebateSession, OpeningArgumentCard, OpeningFramework
from debate_agent.infrastructure.llm_client import DebateLLMClient
from debate_agent.infrastructure.settings import load_settings
from debate_agent.orchestration.pipeline import create_demo_profile
from debate_agent.orchestration.preparation import PreparationCoordinator, ResearchScoutAgent, TheorySynthesisAgent
from debate_agent.orchestration.turn_pipeline import TurnPipeline
from debate_agent.storage.json_store import JSONSessionStore


class SessionCreatePayload(BaseModel):
    topic: str = Field(min_length=1)
    user_side: str = Field(default="正方", min_length=1)
    agent_side: str = Field(default="反方", min_length=1)
    coach_feedback_mode: str = Field(default=CoachFeedbackMode.MANUAL.value)
    web_search_enabled: bool = True
    default_closing_side: str = Field(default="opponent")


class TurnPayload(BaseModel):
    user_text: str = Field(min_length=1)
    include_coach_feedback: bool | None = None


class ClosingPayload(BaseModel):
    speaker_side: str | None = None
    closing_focus: str | None = None


class InquiryPayload(BaseModel):
    speaker_side: str | None = None
    inquiry_focus: str | None = None
    max_questions: int = Field(default=4, ge=3, le=8)


class TimerPlanPayload(BaseModel):
    speaker_side: str | None = None
    phase: str | None = None
    note: str | None = None


class PreparationPayload(BaseModel):
    preparation_goal: str | None = None
    focus: str | None = None
    limit: int = Field(default=6, ge=3, le=10)


class OpeningBriefGeneratePayload(BaseModel):
    speaker_side: str | None = None
    brief_focus: str | None = None
    target_duration_minutes: int = Field(default=3, ge=1, le=8)


class OpeningFrameworkGeneratePayload(BaseModel):
    speaker_side: str | None = None
    brief_focus: str | None = None


class OpeningArgumentCardPayload(BaseModel):
    claim: str = ""
    data_support: str = ""
    academic_support: str = ""
    scenario_support: str = ""


class OpeningFrameworkPayload(BaseModel):
    judge_standard: str = ""
    framework_summary: str = ""
    argument_cards: list[OpeningArgumentCardPayload] = Field(default_factory=list)


class OpeningBriefFromFrameworkPayload(OpeningBriefGeneratePayload):
    framework: OpeningFrameworkPayload | None = None


class OpeningBriefImportPayload(BaseModel):
    speaker_side: str | None = None
    spoken_text: str = Field(min_length=1)
    strategy_summary: str | None = None
    outline: list[str] | None = None
    framework: OpeningFrameworkPayload | None = None
    target_duration_minutes: int | None = Field(default=None, ge=1, le=8)


class SessionOptionsPayload(BaseModel):
    coach_feedback_mode: str | None = None
    web_search_enabled: bool | None = None
    default_closing_side: str | None = None


class SessionMetadataPayload(BaseModel):
    topic: str | None = None
    user_side: str | None = None
    agent_side: str | None = None


class SessionPhasePayload(BaseModel):
    phase: str = Field(min_length=1)


def create_app(
    application: DebateApplication | None = None,
    profile: DebateProfile | None = None,
) -> FastAPI:
    debate_application = application or _build_application()
    debate_profile = profile or create_demo_profile()
    assets_dir = Path(__file__).resolve().parent / "web_assets"

    app = FastAPI(title="Debate Project Web UI", version="0.1.0")
    app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(assets_dir / "index.html")

    @app.get("/api/health")
    def health() -> dict[str, object]:
        llm_client = debate_application.pipeline.llm_client
        llm_enabled = llm_client is not None
        return {
            "status": "ok",
            "llm_enabled": llm_enabled,
            "model": llm_client.settings.model if llm_enabled else None,
        }

    @app.get("/api/sessions")
    def list_sessions() -> list[dict[str, object]]:
        sessions: list[dict[str, object]] = []
        for session_id in debate_application.list_session_ids():
            session = debate_application.load_session(session_id)
            sessions.append(_serialize_session_summary(debate_application, session))
        return sessions

    @app.post("/api/sessions")
    def create_session(payload: SessionCreatePayload) -> dict[str, object]:
        mode = _parse_coach_mode(payload.coach_feedback_mode)
        result = debate_application.create_session(
            NewSessionRequest(
                topic=payload.topic,
                user_side=payload.user_side,
                agent_side=payload.agent_side,
                profile_id=debate_profile.profile_id,
                coach_feedback_mode=mode,
                web_search_enabled=payload.web_search_enabled,
                default_closing_side=_normalize_closing_side(payload.default_closing_side),
            )
        )
        return _serialize_session_result(debate_application, result.session)

    @app.get("/api/sessions/{session_id}")
    def get_session(session_id: str) -> dict[str, object]:
        session = _load_session_or_404(debate_application, session_id)
        return _serialize_session_result(debate_application, session)

    @app.delete("/api/sessions/{session_id}")
    def delete_session(session_id: str) -> dict[str, object]:
        _load_session_or_404(debate_application, session_id)
        result = debate_application.delete_session(session_id)
        return {
            "session_id": result.session_id,
            "deleted_path": str(result.deleted_path),
        }

    @app.post("/api/sessions/{session_id}/turns")
    def create_turn(session_id: str, payload: TurnPayload) -> dict[str, object]:
        session = _load_session_or_404(debate_application, session_id)
        result = debate_application.process_user_turn(
            session=session,
            profile=debate_profile,
            user_text=payload.user_text,
            include_coach_feedback=payload.include_coach_feedback,
        )
        return {
            "session": _serialize_session_result(debate_application, result.session),
            "turn_result": jsonable_encoder(result.turn_result),
            "saved_path": str(result.saved_path),
        }

    @app.post("/api/sessions/{session_id}/coach")
    def request_coach(session_id: str) -> dict[str, object]:
        session = _load_session_or_404(debate_application, session_id)
        result = debate_application.request_coach_feedback(session, debate_profile)
        if result is None:
            raise HTTPException(status_code=400, detail="至少完成一轮交锋后才能生成教练反馈。")
        return {
            "session": _serialize_session_result(debate_application, result.session),
            "coach_result": jsonable_encoder(result.coach_result),
            "saved_path": str(result.saved_path),
        }

    @app.post("/api/sessions/{session_id}/closing")
    def request_closing(session_id: str, payload: ClosingPayload) -> dict[str, object]:
        session = _load_session_or_404(debate_application, session_id)
        result = debate_application.request_closing_statement(
            session=session,
            profile=debate_profile,
            speaker_side=_normalize_optional_closing_side(payload.speaker_side),
            closing_focus=payload.closing_focus,
        )
        if result is None:
            raise HTTPException(status_code=400, detail="至少完成一轮交锋后才能生成陈词。")
        return {
            "session": _serialize_session_result(debate_application, result.session),
            "closing_result": jsonable_encoder(result.closing_result),
            "saved_path": str(result.saved_path),
        }

    @app.post("/api/sessions/{session_id}/inquiry")
    def request_inquiry(session_id: str, payload: InquiryPayload) -> dict[str, object]:
        session = _load_session_or_404(debate_application, session_id)
        result = debate_application.request_inquiry_strategy(
            session=session,
            profile=debate_profile,
            speaker_side=_normalize_optional_closing_side(payload.speaker_side),
            inquiry_focus=payload.inquiry_focus,
            max_questions=payload.max_questions,
        )
        return {
            "session": _serialize_session_result(debate_application, result.session),
            "inquiry_result": jsonable_encoder(result.inquiry_result),
            "saved_path": str(result.saved_path),
        }

    @app.post("/api/sessions/{session_id}/timer-plan")
    def request_timer_plan(session_id: str, payload: TimerPlanPayload) -> dict[str, object]:
        session = _load_session_or_404(debate_application, session_id)
        result = debate_application.request_timer_plan(
            session=session,
            speaker_side=_normalize_optional_closing_side(payload.speaker_side),
            phase=_parse_optional_phase(payload.phase),
            note=payload.note,
        )
        return {
            "session": _serialize_session_result(debate_application, result.session),
            "timer_plan": jsonable_encoder(result.timer_plan),
            "saved_path": str(result.saved_path),
        }

    @app.post("/api/sessions/{session_id}/preparation")
    def prepare_session(session_id: str, payload: PreparationPayload) -> dict[str, object]:
        session = _load_session_or_404(debate_application, session_id)
        result = debate_application.prepare_session_research(
            session=session,
            profile=debate_profile,
            preparation_goal=payload.preparation_goal,
            focus=payload.focus,
            limit=payload.limit,
        )
        return {
            "session": _serialize_session_result(debate_application, result.session),
            "preparation_result": jsonable_encoder(result.preparation_result),
            "saved_path": str(result.saved_path),
        }

    @app.post("/api/sessions/{session_id}/opening-framework/generate")
    def generate_opening_framework(session_id: str, payload: OpeningFrameworkGeneratePayload) -> dict[str, object]:
        session = _load_session_or_404(debate_application, session_id)
        result = debate_application.generate_opening_framework(
            session=session,
            profile=debate_profile,
            speaker_side=_normalize_optional_closing_side(payload.speaker_side),
            brief_focus=payload.brief_focus,
        )
        return {
            "session": _serialize_session_result(debate_application, result.session),
            "framework_result": jsonable_encoder(result.framework_result),
            "saved_path": str(result.saved_path),
        }

    @app.patch("/api/sessions/{session_id}/opening-framework")
    def update_opening_framework(session_id: str, payload: OpeningFrameworkPayload) -> dict[str, object]:
        session = _load_session_or_404(debate_application, session_id)
        saved_path = debate_application.update_opening_framework(session, _build_opening_framework(payload))
        return {
            "session": _serialize_session_result(debate_application, session),
            "saved_path": str(saved_path),
        }

    @app.post("/api/sessions/{session_id}/opening-briefs/generate")
    def generate_opening_brief(session_id: str, payload: OpeningBriefFromFrameworkPayload) -> dict[str, object]:
        session = _load_session_or_404(debate_application, session_id)
        framework = _build_opening_framework(payload.framework)
        if framework is not None:
            debate_application.update_opening_framework(session, framework)
        try:
            result = debate_application.generate_opening_brief(
                session=session,
                profile=debate_profile,
                speaker_side=_normalize_optional_closing_side(payload.speaker_side),
                brief_focus=payload.brief_focus,
                target_duration_minutes=payload.target_duration_minutes,
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return {
            "session": _serialize_session_result(debate_application, result.session),
            "opening_result": jsonable_encoder(result.opening_result),
            "saved_path": str(result.saved_path),
        }

    @app.post("/api/sessions/{session_id}/opening-briefs/stream")
    def stream_opening_brief(session_id: str, payload: OpeningBriefFromFrameworkPayload) -> StreamingResponse:
        session = _load_session_or_404(debate_application, session_id)
        framework = _build_opening_framework(payload.framework)
        if framework is not None:
            debate_application.update_opening_framework(session, framework)
        event_queue: Queue[tuple[str, dict[str, Any]]] = Queue()

        def emit(event_name: str, data: dict[str, Any]) -> None:
            event_queue.put((event_name, data))

        def worker() -> None:
            try:
                result = debate_application.stream_opening_brief_from_framework(
                    session=session,
                    profile=debate_profile,
                    speaker_side=_normalize_optional_closing_side(payload.speaker_side),
                    brief_focus=payload.brief_focus,
                    target_duration_minutes=payload.target_duration_minutes,
                    framework=framework,
                    progress_callback=lambda event: emit(str(event.get("event", "stage")), dict(event)),
                )
                encoded_result = {
                    "session": _serialize_session_result(debate_application, result.session),
                    "opening_result": jsonable_encoder(result.opening_result),
                    "saved_path": str(result.saved_path),
                }
                emit("completed", encoded_result)
            except ValueError as error:
                emit("error", {"message": str(error)})
            except Exception as error:  # pragma: no cover - defensive stream guard
                emit("error", {"message": str(error)})

        def event_stream():
            worker_thread = Thread(target=worker, daemon=True)
            worker_thread.start()
            while True:
                try:
                    event_name, data = event_queue.get(timeout=0.4)
                except Empty:
                    if not worker_thread.is_alive():
                        break
                    yield ": keepalive\n\n"
                    continue

                yield _encode_sse_event(event_name, data)
                if event_name in {"completed", "error"}:
                    break

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @app.post("/api/sessions/{session_id}/opening-briefs/import")
    def import_opening_brief(session_id: str, payload: OpeningBriefImportPayload) -> dict[str, object]:
        session = _load_session_or_404(debate_application, session_id)
        result = debate_application.inject_opening_brief(
            session=session,
            speaker_side=session.user_side if _normalize_optional_closing_side(payload.speaker_side) in {None, "user"} else session.agent_side,
            spoken_text=payload.spoken_text,
            strategy_summary=payload.strategy_summary,
            outline=payload.outline,
            framework=_build_opening_framework(payload.framework),
            target_duration_minutes=payload.target_duration_minutes,
        )
        return {
            "session": _serialize_session_result(debate_application, result.session),
            "opening_brief": jsonable_encoder(result.opening_brief),
            "saved_path": str(result.saved_path),
        }

    @app.post("/api/sessions/{session_id}/opening-briefs/coach")
    def coach_opening_brief(session_id: str) -> dict[str, object]:
        session = _load_session_or_404(debate_application, session_id)
        result = debate_application.request_opening_brief_feedback(session, debate_profile)
        if result is None:
            raise HTTPException(status_code=400, detail="请先生成或注入一辩稿后再请求稿件教练反馈。")
        return {
            "session": _serialize_session_result(debate_application, result.session),
            "coach_result": jsonable_encoder(result.coach_result),
            "saved_path": str(result.saved_path),
        }

    @app.patch("/api/sessions/{session_id}/options")
    def update_options(session_id: str, payload: SessionOptionsPayload) -> dict[str, object]:
        session = _load_session_or_404(debate_application, session_id)
        coach_mode = _parse_optional_coach_mode(payload.coach_feedback_mode)
        saved_path = debate_application.update_session_options(
            session=session,
            coach_feedback_mode=coach_mode,
            web_search_enabled=payload.web_search_enabled,
            default_closing_side=_normalize_optional_closing_side(payload.default_closing_side),
        )
        return {
            "session": _serialize_session_result(debate_application, session),
            "saved_path": str(saved_path),
        }

    @app.patch("/api/sessions/{session_id}/metadata")
    def update_metadata(session_id: str, payload: SessionMetadataPayload) -> dict[str, object]:
        session = _load_session_or_404(debate_application, session_id)
        if not any([payload.topic, payload.user_side, payload.agent_side]):
            raise HTTPException(status_code=400, detail="至少提供一个需要更新的字段。")
        saved_path = debate_application.update_session_metadata(
            session=session,
            topic=payload.topic,
            user_side=payload.user_side,
            agent_side=payload.agent_side,
        )
        return {
            "session": _serialize_session_result(debate_application, session),
            "saved_path": str(saved_path),
        }

    @app.patch("/api/sessions/{session_id}/phase")
    def update_phase(session_id: str, payload: SessionPhasePayload) -> dict[str, object]:
        session = _load_session_or_404(debate_application, session_id)
        saved_path = debate_application.update_session_phase(session, _parse_phase(payload.phase))
        return {
            "session": _serialize_session_result(debate_application, session),
            "saved_path": str(saved_path),
        }

    return app


def _build_application() -> DebateApplication:
    llm_client = _build_llm_client()
    store = JSONSessionStore()
    pipeline = TurnPipeline(llm_client=llm_client)
    preparation_coordinator = PreparationCoordinator(
        research_scout=ResearchScoutAgent(evidence_service=pipeline.evidence_service),
        theory_synthesis_agent=TheorySynthesisAgent(llm_client=llm_client, model_name=llm_client.settings.model if llm_client else None),
    )
    return DebateApplication(pipeline=pipeline, store=store, preparation_coordinator=preparation_coordinator)


def _build_llm_client() -> DebateLLMClient | None:
    try:
        settings = load_settings()
    except RuntimeError:
        return None
    return DebateLLMClient(settings)


def _load_session_or_404(application: DebateApplication, session_id: str) -> DebateSession:
    try:
        return application.load_session(session_id)
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail="会话不存在。") from error


def _serialize_session_result(application: DebateApplication, session: DebateSession) -> dict[str, object]:
    payload = jsonable_encoder(session)
    payload["summary"] = _serialize_session_summary(application, session)
    return payload


def _build_opening_framework(payload: OpeningFrameworkPayload | None) -> OpeningFramework | None:
    if payload is None:
        return None

    cards = [
        OpeningArgumentCard(
            claim=card.claim.strip(),
            data_support=card.data_support.strip(),
            academic_support=card.academic_support.strip(),
            scenario_support=card.scenario_support.strip(),
        )
        for card in payload.argument_cards
        if any(
            value.strip()
            for value in [
                card.claim,
                card.data_support,
                card.academic_support,
                card.scenario_support,
            ]
        )
    ]
    if not payload.judge_standard.strip() and not payload.framework_summary.strip() and not cards:
        return None

    return OpeningFramework(
        judge_standard=payload.judge_standard.strip(),
        framework_summary=payload.framework_summary.strip(),
        argument_cards=cards,
    )


def _serialize_session_summary(application: DebateApplication, session: DebateSession) -> dict[str, object]:
    session_path = application.store.session_dir / f"{session.session_id}.json"
    updated_at = session_path.stat().st_mtime if session_path.exists() else None
    return {
        "session_id": session.session_id,
        "topic": session.topic,
        "user_side": session.user_side,
        "agent_side": session.agent_side,
        "current_phase": session.current_phase.value,
        "turn_count": len(session.turns),
        "opening_brief_count": len(session.opening_briefs),
        "timer_plan_count": len(session.timer_plans),
        "preparation_packet_count": len(session.preparation_packets),
        "inquiry_count": len(session.inquiry_outputs),
        "clash_count": len(session.clash_points),
        "coach_mode": session.options.coach_feedback_mode.value,
        "web_search_enabled": session.options.web_search_enabled,
        "default_closing_side": session.options.default_closing_side,
        "updated_at": updated_at,
    }


def _parse_coach_mode(raw_value: str) -> CoachFeedbackMode:
    normalized = (raw_value or CoachFeedbackMode.MANUAL.value).strip().lower()
    if normalized not in {CoachFeedbackMode.MANUAL.value, CoachFeedbackMode.AUTO.value}:
        raise HTTPException(status_code=400, detail="coach_feedback_mode 必须是 manual 或 auto。")
    return CoachFeedbackMode(normalized)


def _parse_optional_coach_mode(raw_value: str | None) -> CoachFeedbackMode | None:
    if raw_value is None:
        return None
    return _parse_coach_mode(raw_value)


def _parse_phase(raw_value: str) -> DebatePhase:
    normalized = (raw_value or DebatePhase.OPENING.value).strip().lower()
    try:
        return DebatePhase(normalized)
    except ValueError as error:
        raise HTTPException(status_code=400, detail="phase 必须是 opening、crossfire、free_debate、closing 或 review。") from error


def _parse_optional_phase(raw_value: str | None) -> DebatePhase | None:
    if raw_value is None:
        return None
    return _parse_phase(raw_value)


def _normalize_closing_side(raw_value: str) -> str:
    normalized = (raw_value or "opponent").strip().lower()
    if normalized in {"me", "user", "self"}:
        return "user"
    return "opponent"


def _normalize_optional_closing_side(raw_value: str | None) -> str | None:
    if raw_value is None:
        return None
    return _normalize_closing_side(raw_value)


app = create_app()


def _encode_sse_event(event_name: str, payload: dict[str, Any]) -> str:
    return f"event: {event_name}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"