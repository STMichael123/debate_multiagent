from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from uuid import uuid4

from debate_agent.domain.models import DebatePhase, DebateSession
from debate_agent.infrastructure.llm_client import DebateLLMClient
from debate_agent.infrastructure.settings import load_settings
from debate_agent.app.service import DebateApplication, NewSessionRequest
from debate_agent.domain.models import CoachFeedbackMode
from debate_agent.orchestration.pipeline import create_demo_profile
from debate_agent.orchestration.pipeline_models import ProcessTurnResult
from debate_agent.orchestration.turn_pipeline import TurnPipeline
from debate_agent.prompts.builders import build_session_state_preview
from debate_agent.storage.json_store import JSONSessionStore


HELP_TEXT = """
可用命令：
/help    查看帮助
/state   查看当前会话状态摘要
/clash   查看当前 clash 列表
/coach   生成教练反馈，或切换 auto/manual
/closing 生成长陈词稿，可指定 me 或 opponent
/history 查看最近几轮发言
/save    立即保存当前会话
/exit    保存并退出
""".strip()


def main() -> None:
    profile = create_demo_profile()
    llm_client = _build_llm_client()
    llm_status = _build_llm_status(llm_client)
    store = JSONSessionStore()
    pipeline = TurnPipeline(llm_client=llm_client)
    application = DebateApplication(pipeline=pipeline, store=store)

    print(f"LLM status: {llm_status}")
    print("Debate CLI 已启动。")
    print("输入 1 新建会话，输入 2 继续已有会话。")

    session = _choose_session(application, profile.profile_id)
    print(f"当前会话: {session.session_id}")
    print(f"辩题: {session.topic}")
    print("输入 /help 查看命令。直接输入你的发言即可开始。")
    _interactive_loop(session=session, application=application, profile=profile)


def _build_llm_client() -> DebateLLMClient | None:
    try:
        settings = load_settings()
    except RuntimeError:
        return None
    return DebateLLMClient(settings)


def _build_llm_status(llm_client: DebateLLMClient | None) -> str:
    if llm_client is None:
        return "disabled (missing local LLM configuration)"
    return f"enabled ({llm_client.settings.model} @ {llm_client.settings.base_url})"


def _choose_session(application: DebateApplication, profile_id: str) -> DebateSession:
    while True:
        choice = _safe_input("选择模式 [1=新建, 2=继续]: ").strip()
        if choice == "/exit":
            raise SystemExit(0)
        if choice in {"", "1"}:
            result = _create_new_session(application, profile_id)
            print(f"已创建新会话并保存到: {result.saved_path}")
            return result.session
        if choice == "2":
            session = _resume_session(application)
            if session is not None:
                return session
            continue
        print("请输入 1 或 2。")


def _resume_session(application: DebateApplication) -> DebateSession | None:
    session_ids = application.list_session_ids()
    if not session_ids:
        print("当前没有可继续的会话。")
        return None

    print("可继续的会话：")
    for index, session_id in enumerate(session_ids, start=1):
        session = application.load_session(session_id)
        print(f"{index}. {session.session_id} | {session.topic} | 回合数 {len(session.turns)}")

    while True:
        raw_value = _safe_input("输入序号继续，或直接回车返回: ").strip()
        if raw_value == "/exit":
            raise SystemExit(0)
        if not raw_value:
            return None
        try:
            index = int(raw_value)
        except ValueError:
            print("请输入有效序号。")
            continue
        if 1 <= index <= len(session_ids):
            session = application.load_session(session_ids[index - 1])
            print(build_session_state_preview(session))
            return session
        print("序号超出范围。")


def _create_new_session(application: DebateApplication, profile_id: str):
    topic = _safe_input("输入辩题 [默认: 人工智能是否应当被强制纳入高中通识教育]: ").strip()
    if topic == "/exit":
        raise SystemExit(0)
    user_side = _safe_input("输入你的立场 [默认: 正方]: ").strip()
    if user_side == "/exit":
        raise SystemExit(0)
    agent_side = _safe_input("输入 agent 立场 [默认: 反方]: ").strip()
    if agent_side == "/exit":
        raise SystemExit(0)
    coach_mode = _safe_input("教练模式 [manual=按需, auto=每轮自动，默认 manual]: ").strip().lower()
    if coach_mode == "/exit":
        raise SystemExit(0)
    web_search = _safe_input("是否启用网页检索 [Y/n，默认 Y]: ").strip().lower()
    if web_search == "/exit":
        raise SystemExit(0)
    closing_side = _safe_input("默认陈词方 [opponent/me，默认 opponent]: ").strip().lower()
    if closing_side == "/exit":
        raise SystemExit(0)
    return application.create_session(
        NewSessionRequest(
            topic=topic or "人工智能是否应当被强制纳入高中通识教育",
            user_side=user_side or "正方",
            agent_side=agent_side or "反方",
            profile_id=profile_id,
            coach_feedback_mode=CoachFeedbackMode.AUTO if coach_mode == "auto" else CoachFeedbackMode.MANUAL,
            web_search_enabled=web_search not in {"n", "no", "false", "0"},
            default_closing_side="user" if closing_side in {"me", "user"} else "opponent",
        )
    )


def _interactive_loop(
    session: DebateSession,
    application: DebateApplication,
    profile,
) -> None:
    while True:
        user_text = _safe_input("\n你> ").strip()
        if not user_text:
            continue
        if user_text.startswith("/"):
            if _handle_command(user_text, session, application, profile):
                return
            continue

        action_result = application.process_user_turn(session, profile, user_text)
        _print_turn_result(action_result.turn_result, action_result.saved_path)


def _handle_command(
    command: str,
    session: DebateSession,
    application: DebateApplication,
    profile,
) -> bool:
    normalized = command.strip()
    normalized_lower = normalized.lower()
    if normalized_lower == "/help":
        print(HELP_TEXT)
        return False
    if normalized_lower == "/state":
        print(build_session_state_preview(session))
        return False
    if normalized_lower == "/clash":
        _print_clash_points(session)
        return False
    if normalized_lower.startswith("/coach"):
        coach_argument = normalized_lower.replace("/coach", "", 1).strip()
        if coach_argument in {"auto", "manual"}:
            mode = CoachFeedbackMode.AUTO if coach_argument == "auto" else CoachFeedbackMode.MANUAL
            path = application.update_coach_feedback_mode(session, mode)
            print(f"教练模式已更新为: {mode.value}")
            print(f"已自动保存: {path}")
            return False
        action_result = application.request_coach_feedback(session, profile)
        if action_result is None:
            print("至少完成一轮用户发言和对手回应后，才能生成教练反馈。")
            return False
        print(json.dumps(asdict(action_result.coach_result.coach_report), ensure_ascii=False, indent=2))
        print(f"已自动保存: {action_result.saved_path}")
        if action_result.coach_result.used_cached:
            print("本次返回的是当前最新回合的已生成教练反馈。")
        elif action_result.coach_result.model_name:
            print(f"教练模型: {action_result.coach_result.model_name}")
        else:
            print("教练反馈由本地 fallback 生成。")
        return False
    if normalized_lower.startswith("/closing"):
        closing_argument = normalized_lower.replace("/closing", "", 1).strip()
        speaker_side = "user" if closing_argument in {"me", "user"} else None
        if closing_argument in {"opponent", "agent"}:
            speaker_side = "opponent"
        action_result = application.request_closing_statement(session, profile, speaker_side=speaker_side)
        if action_result is None:
            print("当前材料还不足以生成陈词，至少先完成一轮交锋。")
            return False
        print("\nClosing Agent>")
        print(action_result.closing_result.closing_output.spoken_text)
        print(f"\n已自动保存: {action_result.saved_path}")
        if action_result.closing_result.model_name:
            print(f"陈词模型: {action_result.closing_result.model_name}")
        else:
            print("陈词稿由本地 fallback 生成。")
        return False
    if normalized_lower == "/history":
        _print_history(session)
        return False
    if normalized_lower == "/save":
        path = application.save_session(session)
        print(f"已保存: {path}")
        return False
    if normalized_lower == "/exit":
        path = application.save_session(session)
        print(f"会话已保存并退出: {path}")
        return True

    print("未知命令，输入 /help 查看可用命令。")
    return False


def _print_turn_result(result: ProcessTurnResult, saved_path: Path) -> None:
    print("\nOpponent>")
    print(result.opponent_output.spoken_text)
    if result.opponent_output.follow_up_questions:
        print("\n追问:")
        for question in result.opponent_output.follow_up_questions:
            print(f"- {question}")
    if result.coach_report is not None:
        print("\nCoach>")
        print(result.coach_report.round_verdict)
        if result.coach_report.improvement_actions:
            print("改进建议:")
            for action in result.coach_report.improvement_actions[:3]:
                print(f"- {action}")
    else:
        print("\n需要教练反馈时，输入 /coach。")
    print(f"\n已自动保存: {saved_path}")


def _print_clash_points(session: DebateSession) -> None:
    if not session.clash_points:
        print("当前没有 clash。")
        return
    for index, clash in enumerate(session.clash_points, start=1):
        print(f"[{index}] {clash.topic_label}")
        print(f"摘要: {clash.summary}")
        print(f"用户论点数: {len(clash.user_argument_ids)} | 对手论点数: {len(clash.agent_argument_ids)}")
        if clash.open_questions:
            print("待追问:")
            for question in clash.open_questions[:3]:
                print(f"- {question}")
        print("")


def _print_history(session: DebateSession, limit: int = 6) -> None:
    if not session.turns:
        print("当前没有历史回合。")
        return
    for turn in session.turns[-limit:]:
        print(f"[{turn.speaker_role.value}] {turn.raw_text}")


def _safe_input(prompt: str) -> str:
    try:
        return input(prompt)
    except EOFError:
        return "/exit"


if __name__ == "__main__":
    main()