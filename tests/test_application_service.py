from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from debate_agent.app.service import DebateApplication, NewSessionRequest
from debate_agent.domain.models import CoachFeedbackMode, DebatePhase, OpeningArgumentCard, OpeningFramework
from debate_agent.orchestration.pipeline import create_demo_profile
from debate_agent.orchestration.turn_pipeline import TurnPipeline
from debate_agent.storage.json_store import JSONSessionStore


class DebateApplicationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.profile = create_demo_profile()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store = JSONSessionStore(session_dir=Path(self.temp_dir.name))
        self.application = DebateApplication(pipeline=TurnPipeline(enable_web_search=False), store=self.store)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_manual_coach_mode_keeps_turn_flow_clean(self) -> None:
        session_result = self.application.create_session(
            NewSessionRequest(
                topic="人工智能是否应当被强制纳入高中通识教育",
                user_side="正方",
                agent_side="反方",
                profile_id=self.profile.profile_id,
            )
        )

        turn_action = self.application.process_user_turn(
            session=session_result.session,
            profile=self.profile,
            user_text="我方认为 AI 教育应该强制推进，因为它是未来基础素养。",
        )

        self.assertEqual(turn_action.session.options.coach_feedback_mode, CoachFeedbackMode.MANUAL)
        self.assertIsNone(turn_action.turn_result.coach_report)
        self.assertEqual(len(turn_action.session.coach_reports), 0)

        coach_action = self.application.request_coach_feedback(turn_action.session, self.profile)
        self.assertIsNotNone(coach_action)
        assert coach_action is not None
        self.assertEqual(len(coach_action.session.coach_reports), 1)

    def test_auto_coach_mode_generates_feedback_during_turn(self) -> None:
        session_result = self.application.create_session(
            NewSessionRequest(
                topic="人工智能是否应当被强制纳入高中通识教育",
                user_side="正方",
                agent_side="反方",
                profile_id=self.profile.profile_id,
                coach_feedback_mode=CoachFeedbackMode.AUTO,
            )
        )

        turn_action = self.application.process_user_turn(
            session=session_result.session,
            profile=self.profile,
            user_text="我方认为 AI 教育应该强制推进，因为它是未来基础素养。",
        )

        self.assertIsNotNone(turn_action.turn_result.coach_report)
        self.assertEqual(len(turn_action.session.coach_reports), 1)

    def test_closing_statement_can_target_user_side(self) -> None:
        session_result = self.application.create_session(
            NewSessionRequest(
                topic="人工智能是否应当被强制纳入高中通识教育",
                user_side="正方",
                agent_side="反方",
                profile_id=self.profile.profile_id,
                default_closing_side="user",
            )
        )
        self.application.process_user_turn(
            session=session_result.session,
            profile=self.profile,
            user_text="我方认为 AI 教育应该强制推进，因为它是未来基础素养。",
        )

        closing_action = self.application.request_closing_statement(
            session=session_result.session,
            profile=self.profile,
            speaker_side="user",
        )

        self.assertIsNotNone(closing_action)
        assert closing_action is not None
        self.assertEqual(closing_action.closing_result.closing_output.speaker_side, session_result.session.user_side)
        self.assertEqual(len(closing_action.session.closing_outputs), 1)

    def test_user_closing_can_be_generated_without_turns(self) -> None:
        session_result = self.application.create_session(
            NewSessionRequest(
                topic="人工智能是否应当被强制纳入高中通识教育",
                user_side="正方",
                agent_side="反方",
                profile_id=self.profile.profile_id,
                default_closing_side="user",
            )
        )

        closing_action = self.application.request_closing_statement(
            session=session_result.session,
            profile=self.profile,
            speaker_side="user",
        )

        self.assertIsNotNone(closing_action)
        assert closing_action is not None
        self.assertEqual(closing_action.closing_result.closing_output.speaker_side, "正方")
        self.assertGreater(len(closing_action.closing_result.closing_output.spoken_text), 0)
        self.assertIn("举证效力排序规则", closing_action.closing_result.closing_prompt)
        self.assertIn("具体数据", closing_action.closing_result.closing_prompt)
        self.assertIn("学理研究", closing_action.closing_result.closing_prompt)
        self.assertIn("辩论稿转载", closing_action.closing_result.closing_prompt)
        self.assertIn("学理机制 + 生活情景", closing_action.closing_result.closing_prompt)

    def test_session_round_trip_preserves_options(self) -> None:
        session_result = self.application.create_session(
            NewSessionRequest(
                topic="测试辩题",
                user_side="正方",
                agent_side="反方",
                profile_id=self.profile.profile_id,
                coach_feedback_mode=CoachFeedbackMode.AUTO,
                web_search_enabled=False,
                default_closing_side="user",
            )
        )

        loaded = self.application.load_session(session_result.session.session_id)
        self.assertEqual(loaded.current_phase, DebatePhase.OPENING)
        self.assertEqual(loaded.options.coach_feedback_mode, CoachFeedbackMode.AUTO)
        self.assertFalse(loaded.options.web_search_enabled)
        self.assertEqual(loaded.options.default_closing_side, "user")

    def test_update_session_phase(self) -> None:
        session_result = self.application.create_session(
            NewSessionRequest(
                topic="测试辩题",
                user_side="正方",
                agent_side="反方",
                profile_id=self.profile.profile_id,
            )
        )

        self.application.update_session_phase(session_result.session, DebatePhase.CROSSFIRE)
        loaded = self.application.load_session(session_result.session.session_id)
        self.assertEqual(loaded.current_phase, DebatePhase.CROSSFIRE)

    def test_update_session_metadata(self) -> None:
        session_result = self.application.create_session(
            NewSessionRequest(
                topic="旧辩题",
                user_side="正方",
                agent_side="反方",
                profile_id=self.profile.profile_id,
            )
        )

        self.application.update_session_metadata(
            session=session_result.session,
            topic="新辩题",
            user_side="支持方",
            agent_side="反对方",
        )

        loaded = self.application.load_session(session_result.session.session_id)
        self.assertEqual(loaded.topic, "新辩题")
        self.assertEqual(loaded.user_side, "支持方")
        self.assertEqual(loaded.agent_side, "反对方")

    def test_delete_session_removes_persisted_file(self) -> None:
        session_result = self.application.create_session(
            NewSessionRequest(
                topic="待删除辩题",
                user_side="正方",
                agent_side="反方",
                profile_id=self.profile.profile_id,
            )
        )

        delete_result = self.application.delete_session(session_result.session.session_id)

        self.assertEqual(delete_result.session_id, session_result.session.session_id)
        self.assertFalse(delete_result.deleted_path.exists())
        with self.assertRaises(FileNotFoundError):
            self.application.load_session(session_result.session.session_id)

    def test_opening_brief_can_be_generated_and_used_as_debate_context(self) -> None:
        session_result = self.application.create_session(
            NewSessionRequest(
                topic="人工智能是否应当被强制纳入高中通识教育",
                user_side="正方",
                agent_side="反方",
                profile_id=self.profile.profile_id,
            )
        )

        opening_action = self.application.generate_opening_brief(
            session=session_result.session,
            profile=self.profile,
            speaker_side="user",
            target_duration_minutes=3,
        )

        self.assertTrue(opening_action.opening_result.opening_brief.spoken_text)
        self.assertEqual(len(opening_action.session.opening_briefs), 1)
        self.assertIsNotNone(opening_action.opening_result.opening_brief.framework)
        assert opening_action.opening_result.opening_brief.framework is not None
        self.assertGreaterEqual(len(opening_action.opening_result.opening_brief.framework.argument_cards), 2)
        self.assertEqual(opening_action.opening_result.opening_brief.target_duration_minutes, 3)
        self.assertEqual(opening_action.opening_result.opening_brief.target_word_count, 900)
        self.assertIsNotNone(opening_action.session.current_opening_framework)

        turn_action = self.application.process_user_turn(
            session=session_result.session,
            profile=self.profile,
            user_text="我方进一步强调，强制纳入能避免基础能力分化。",
        )

        self.assertIn("当前用户一辩稿骨架", turn_action.turn_result.opponent_prompt)
        self.assertIn("一辩稿", turn_action.turn_result.opponent_prompt)

    def test_opening_framework_can_be_generated_and_persisted_independently(self) -> None:
        session_result = self.application.create_session(
            NewSessionRequest(
                topic="人工智能是否应当被强制纳入高中通识教育",
                user_side="正方",
                agent_side="反方",
                profile_id=self.profile.profile_id,
            )
        )

        framework_action = self.application.generate_opening_framework(
            session=session_result.session,
            profile=self.profile,
            speaker_side="user",
        )

        self.assertTrue(framework_action.framework_result.framework.judge_standard)
        self.assertGreaterEqual(len(framework_action.framework_result.framework.argument_cards), 2)
        self.assertEqual(len(framework_action.session.opening_briefs), 0)
        self.assertIsNotNone(framework_action.session.current_opening_framework)

        loaded = self.application.load_session(session_result.session.session_id)
        self.assertIsNotNone(loaded.current_opening_framework)
        assert loaded.current_opening_framework is not None
        self.assertEqual(
            loaded.current_opening_framework.framework_summary,
            framework_action.framework_result.framework.framework_summary,
        )

    def test_opening_brief_can_be_injected_and_coached(self) -> None:
        session_result = self.application.create_session(
            NewSessionRequest(
                topic="短视频平台是否应加强未成年人使用限制",
                user_side="正方",
                agent_side="反方",
                profile_id=self.profile.profile_id,
            )
        )

        import_action = self.application.inject_opening_brief(
            session=session_result.session,
            speaker_side="正方",
            spoken_text="各位评判，今天本题应比较未成年人保护的必要性与平台治理责任。",
        )
        coach_action = self.application.request_opening_brief_feedback(import_action.session, self.profile)

        self.assertIsNotNone(coach_action)
        assert coach_action is not None
        self.assertEqual(import_action.opening_brief.source_mode, "manual")
        self.assertEqual(coach_action.coach_result.coach_report.scope, "opening_brief")

    def test_injected_opening_brief_can_preserve_framework(self) -> None:
        session_result = self.application.create_session(
            NewSessionRequest(
                topic="短视频平台是否应加强未成年人使用限制",
                user_side="正方",
                agent_side="反方",
                profile_id=self.profile.profile_id,
            )
        )

        framework = OpeningFramework(
            judge_standard="比较哪一方更能降低未成年人沉迷风险且把治理误伤压到最低。",
            framework_summary="先定保护标准，再论证限制措施的必要性、精准性与可执行性。",
            argument_cards=[
                OpeningArgumentCard(
                    claim="平台端限制比家庭零散管理更稳定地降低高频沉迷暴露。",
                    data_support="当前缺少可直接上场的硬证据。",
                    academic_support="未成年人自控尚未成熟，平台默认机制会放大即时反馈依赖。",
                    scenario_support="当学生深夜连续刷短视频时，平台端上限比家长口头劝阻更可执行。",
                )
            ],
        )

        import_action = self.application.inject_opening_brief(
            session=session_result.session,
            speaker_side="正方",
            spoken_text="各位评判，今天本题应比较哪一方更能降低沉迷风险并减少治理误伤。",
            framework=framework,
            target_duration_minutes=4,
        )

        self.assertIsNotNone(import_action.opening_brief.framework)
        assert import_action.opening_brief.framework is not None
        self.assertEqual(import_action.opening_brief.framework.judge_standard, framework.judge_standard)
        self.assertEqual(import_action.opening_brief.target_duration_minutes, 4)
        self.assertEqual(import_action.opening_brief.outline, ["平台端限制比家庭零散管理更稳定地降低..."])


if __name__ == "__main__":
    unittest.main()