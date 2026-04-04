from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from debate_agent.app.service import DebateApplication
from debate_agent.app.web import create_app
from debate_agent.orchestration.pipeline import create_demo_profile
from debate_agent.orchestration.preparation import PreparationCoordinator, ResearchScoutAgent, TheorySynthesisAgent
from debate_agent.orchestration.turn_pipeline import TurnPipeline
from debate_agent.storage.json_store import JSONSessionStore


class WebAppTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store = JSONSessionStore(session_dir=Path(self.temp_dir.name))
        self.pipeline = TurnPipeline(enable_web_search=False)
        self.preparation_coordinator = PreparationCoordinator(
            research_scout=ResearchScoutAgent(evidence_service=self.pipeline.evidence_service),
            theory_synthesis_agent=TheorySynthesisAgent(),
        )
        self.application = DebateApplication(
            pipeline=self.pipeline,
            store=self.store,
            preparation_coordinator=self.preparation_coordinator,
        )
        self.profile = create_demo_profile()
        self.client = TestClient(create_app(application=self.application, profile=self.profile))

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_create_session_and_process_turn_via_api(self) -> None:
        create_response = self.client.post(
            "/api/sessions",
            json={
                "topic": "人工智能是否应当被强制纳入高中通识教育",
                "user_side": "正方",
                "agent_side": "反方",
                "coach_feedback_mode": "manual",
                "web_search_enabled": True,
                "default_closing_side": "opponent",
            },
        )
        self.assertEqual(create_response.status_code, 200)
        session_payload = create_response.json()
        session_id = session_payload["session_id"]

        turn_response = self.client.post(
            f"/api/sessions/{session_id}/turns",
            json={"user_text": "我方认为 AI 教育应该成为所有高中生的基础能力训练。"},
        )
        self.assertEqual(turn_response.status_code, 200)
        payload = turn_response.json()
        self.assertEqual(payload["session"]["summary"]["turn_count"], 2)
        self.assertIn("opponent_output", payload["turn_result"])
        self.assertEqual(payload["turn_result"]["master_plan"]["selected_agent"], "debate")
        self.assertEqual(payload["turn_result"]["timer_plan"]["source"], "automation")

    def test_update_options_endpoint(self) -> None:
        create_response = self.client.post(
            "/api/sessions",
            json={
                "topic": "测试辩题",
                "user_side": "正方",
                "agent_side": "反方",
                "coach_feedback_mode": "manual",
                "web_search_enabled": True,
                "default_closing_side": "opponent",
            },
        )
        session_id = create_response.json()["session_id"]

        update_response = self.client.patch(
            f"/api/sessions/{session_id}/options",
            json={
                "coach_feedback_mode": "auto",
                "web_search_enabled": False,
                "default_closing_side": "user",
            },
        )
        self.assertEqual(update_response.status_code, 200)
        session_payload = update_response.json()["session"]
        self.assertEqual(session_payload["options"]["coach_feedback_mode"], "auto")
        self.assertFalse(session_payload["options"]["web_search_enabled"])
        self.assertEqual(session_payload["options"]["default_closing_side"], "user")

    def test_update_metadata_endpoint(self) -> None:
        create_response = self.client.post(
            "/api/sessions",
            json={
                "topic": "旧辩题",
                "user_side": "正方",
                "agent_side": "反方",
                "coach_feedback_mode": "manual",
                "web_search_enabled": True,
                "default_closing_side": "opponent",
            },
        )
        session_id = create_response.json()["session_id"]

        update_response = self.client.patch(
            f"/api/sessions/{session_id}/metadata",
            json={
                "topic": "新辩题",
                "user_side": "支持方",
                "agent_side": "反对方",
            },
        )
        self.assertEqual(update_response.status_code, 200)
        session_payload = update_response.json()["session"]
        self.assertEqual(session_payload["topic"], "新辩题")
        self.assertEqual(session_payload["user_side"], "支持方")
        self.assertEqual(session_payload["agent_side"], "反对方")

    def test_update_phase_endpoint(self) -> None:
        create_response = self.client.post(
            "/api/sessions",
            json={
                "topic": "阶段切换测试",
                "user_side": "正方",
                "agent_side": "反方",
                "coach_feedback_mode": "manual",
                "web_search_enabled": True,
                "default_closing_side": "opponent",
            },
        )
        session_id = create_response.json()["session_id"]
        self.assertEqual(create_response.json()["summary"]["current_phase"], "opening")

        update_response = self.client.patch(
            f"/api/sessions/{session_id}/phase",
            json={"phase": "crossfire"},
        )
        self.assertEqual(update_response.status_code, 200)
        session_payload = update_response.json()["session"]
        self.assertEqual(session_payload["current_phase"], "crossfire")
        self.assertEqual(session_payload["summary"]["current_phase"], "crossfire")

    def test_user_closing_can_be_requested_before_first_turn(self) -> None:
        create_response = self.client.post(
            "/api/sessions",
            json={
                "topic": "人工智能是否应当被强制纳入高中通识教育",
                "user_side": "正方",
                "agent_side": "反方",
                "coach_feedback_mode": "manual",
                "web_search_enabled": True,
                "default_closing_side": "user",
            },
        )
        session_id = create_response.json()["session_id"]

        closing_response = self.client.post(
            f"/api/sessions/{session_id}/closing",
            json={"speaker_side": "user"},
        )
        self.assertEqual(closing_response.status_code, 200)
        payload = closing_response.json()
        self.assertEqual(payload["closing_result"]["closing_output"]["speaker_side"], "正方")
        self.assertTrue(payload["closing_result"]["closing_output"]["spoken_text"])
        self.assertEqual(payload["closing_result"]["master_plan"]["selected_agent"], "speech")

    def test_inquiry_endpoint_returns_master_plan_and_questions(self) -> None:
        create_response = self.client.post(
            "/api/sessions",
            json={
                "topic": "人工智能是否应当被强制纳入高中通识教育",
                "user_side": "正方",
                "agent_side": "反方",
                "coach_feedback_mode": "manual",
                "web_search_enabled": True,
                "default_closing_side": "opponent",
            },
        )
        session_id = create_response.json()["session_id"]

        self.client.post(
            f"/api/sessions/{session_id}/turns",
            json={"user_text": "我方认为 AI 教育应该成为所有高中生的基础能力训练。"},
        )

        inquiry_response = self.client.post(
            f"/api/sessions/{session_id}/inquiry",
            json={"speaker_side": "opponent", "max_questions": 4},
        )
        self.assertEqual(inquiry_response.status_code, 200)
        payload = inquiry_response.json()
        self.assertEqual(payload["inquiry_result"]["master_plan"]["selected_agent"], "inquiry")
        self.assertTrue(payload["inquiry_result"]["inquiry_output"]["questions"])
        self.assertEqual(payload["session"]["summary"]["inquiry_count"], 1)
        self.assertGreaterEqual(payload["session"]["summary"]["timer_plan_count"], 2)

    def test_timer_plan_endpoint_returns_oversight_data(self) -> None:
        create_response = self.client.post(
            "/api/sessions",
            json={
                "topic": "人工智能是否应当被强制纳入高中通识教育",
                "user_side": "正方",
                "agent_side": "反方",
                "coach_feedback_mode": "manual",
                "web_search_enabled": True,
                "default_closing_side": "opponent",
            },
        )
        session_id = create_response.json()["session_id"]

        timer_response = self.client.post(
            f"/api/sessions/{session_id}/timer-plan",
            json={"speaker_side": "user", "phase": "closing", "note": "测试接口计时规划"},
        )
        self.assertEqual(timer_response.status_code, 200)
        payload = timer_response.json()
        self.assertEqual(payload["timer_plan"]["phase"], "closing")
        self.assertEqual(payload["timer_plan"]["speaker_side"], "正方")
        self.assertEqual(payload["timer_plan"]["source"], "automation")
        self.assertEqual(payload["session"]["summary"]["timer_plan_count"], 1)

    def test_preparation_endpoint_returns_research_and_theory_packet(self) -> None:
        create_response = self.client.post(
            "/api/sessions",
            json={
                "topic": "人工智能是否应当被强制纳入高中通识教育",
                "user_side": "正方",
                "agent_side": "反方",
                "coach_feedback_mode": "manual",
                "web_search_enabled": False,
                "default_closing_side": "opponent",
            },
        )
        session_id = create_response.json()["session_id"]

        preparation_response = self.client.post(
            f"/api/sessions/{session_id}/preparation",
            json={"focus": "官方 数据 研究", "limit": 5},
        )
        self.assertEqual(preparation_response.status_code, 200)
        payload = preparation_response.json()
        self.assertTrue(payload["preparation_result"]["preparation_packet"]["argument_seeds"])
        self.assertTrue(payload["preparation_result"]["preparation_packet"]["theory_points"])
        self.assertEqual(payload["session"]["summary"]["preparation_packet_count"], 1)

    def test_preparation_packet_is_consumed_by_turn_api(self) -> None:
        create_response = self.client.post(
            "/api/sessions",
            json={
                "topic": "人工智能是否应当被强制纳入高中通识教育",
                "user_side": "正方",
                "agent_side": "反方",
                "coach_feedback_mode": "manual",
                "web_search_enabled": False,
                "default_closing_side": "opponent",
            },
        )
        session_id = create_response.json()["session_id"]

        preparation_response = self.client.post(
            f"/api/sessions/{session_id}/preparation",
            json={"focus": "官方 数据 研究", "limit": 5},
        )
        preparation_payload = preparation_response.json()

        turn_response = self.client.post(
            f"/api/sessions/{session_id}/turns",
            json={"user_text": "我方主张强制纳入能稳定补齐学生的 AI 基础能力。"},
        )
        self.assertEqual(turn_response.status_code, 200)
        payload = turn_response.json()
        self.assertIn("当前可复用的备赛资料包", payload["turn_result"]["opponent_prompt"])
        self.assertIn(preparation_payload["preparation_result"]["preparation_packet"]["argument_seeds"][0], payload["turn_result"]["opponent_prompt"])

    def test_delete_session_endpoint(self) -> None:
        create_response = self.client.post(
            "/api/sessions",
            json={
                "topic": "待删除辩题",
                "user_side": "正方",
                "agent_side": "反方",
                "coach_feedback_mode": "manual",
                "web_search_enabled": True,
                "default_closing_side": "opponent",
            },
        )
        session_id = create_response.json()["session_id"]

        delete_response = self.client.delete(f"/api/sessions/{session_id}")
        self.assertEqual(delete_response.status_code, 200)
        self.assertEqual(delete_response.json()["session_id"], session_id)

        fetch_response = self.client.get(f"/api/sessions/{session_id}")
        self.assertEqual(fetch_response.status_code, 404)

    def test_opening_brief_generate_import_and_coach_endpoints(self) -> None:
        create_response = self.client.post(
            "/api/sessions",
            json={
                "topic": "人工智能是否应当被强制纳入高中通识教育",
                "user_side": "正方",
                "agent_side": "反方",
                "coach_feedback_mode": "manual",
                "web_search_enabled": True,
                "default_closing_side": "user",
            },
        )
        session_id = create_response.json()["session_id"]

        generate_response = self.client.post(
            f"/api/sessions/{session_id}/opening-briefs/generate",
            json={"speaker_side": "user", "target_duration_minutes": 4},
        )
        self.assertEqual(generate_response.status_code, 200)
        opening_brief = generate_response.json()["opening_result"]["opening_brief"]
        self.assertTrue(opening_brief["spoken_text"])
        self.assertEqual(opening_brief["target_duration_minutes"], 4)
        self.assertIsNotNone(opening_brief["framework"])
        import_response = self.client.post(
            f"/api/sessions/{session_id}/opening-briefs/import",
            json={
                "speaker_side": "user",
                "spoken_text": "各位评判，本题应比较政策净收益。",
                "target_duration_minutes": 4,
                "framework": {
                    "judge_standard": "比较哪一方更能提升教育效果并控制资源挤出。",
                    "framework_summary": "先定标准，再论证能力提升、教育公平与执行成本。",
                    "argument_cards": [
                        {
                            "claim": "把 AI 纳入通识教育能让学生获得最低限度的技术理解能力。",
                            "data_support": "当前缺少可直接上场的硬证据。",
                            "academic_support": "通识教育的任务是建立基础认知框架，而非职业技能训练。",
                            "scenario_support": "学生面对 AI 生成内容时，若没有基础辨识能力，就更容易误判信息。"
                        }
                    ]
                }
            },
        )
        self.assertEqual(import_response.status_code, 200)
        self.assertEqual(import_response.json()["opening_brief"]["source_mode"], "manual")
        self.assertEqual(import_response.json()["opening_brief"]["target_duration_minutes"], 4)
        self.assertEqual(import_response.json()["opening_brief"]["framework"]["judge_standard"], "比较哪一方更能提升教育效果并控制资源挤出。")

        coach_response = self.client.post(f"/api/sessions/{session_id}/opening-briefs/coach")
        self.assertEqual(coach_response.status_code, 200)
        self.assertEqual(coach_response.json()["coach_result"]["coach_report"]["scope"], "opening_brief")

    def test_opening_framework_generate_and_update_endpoints(self) -> None:
        create_response = self.client.post(
            "/api/sessions",
            json={
                "topic": "人工智能是否应当被强制纳入高中通识教育",
                "user_side": "正方",
                "agent_side": "反方",
                "coach_feedback_mode": "manual",
                "web_search_enabled": True,
                "default_closing_side": "user",
            },
        )
        session_id = create_response.json()["session_id"]

        framework_response = self.client.post(
            f"/api/sessions/{session_id}/opening-framework/generate",
            json={"speaker_side": "user"},
        )
        self.assertEqual(framework_response.status_code, 200)
        framework_payload = framework_response.json()["framework_result"]["framework"]
        self.assertTrue(framework_payload["judge_standard"])
        self.assertGreaterEqual(len(framework_payload["argument_cards"]), 2)
        self.assertEqual(framework_response.json()["session"]["current_opening_framework"]["judge_standard"], framework_payload["judge_standard"])

        update_response = self.client.patch(
            f"/api/sessions/{session_id}/opening-framework",
            json={
                "judge_standard": "比较哪一方更能稳定提升学生 AI 基础能力并控制资源挤出。",
                "framework_summary": "先定标准，再比较基础能力、教育公平与执行成本。",
                "argument_cards": [
                    {
                        "claim": "通识教育的最低目标是让学生具备识别和使用 AI 工具的基础能力。",
                        "data_support": "当前缺少可直接上场的硬证据。",
                        "academic_support": "通识教育强调面向全体学生的基础认知能力建设。",
                        "scenario_support": "学生在面对 AI 生成内容时，如果没有基础识读能力，就更容易误信错误信息。"
                    }
                ]
            },
        )
        self.assertEqual(update_response.status_code, 200)
        self.assertEqual(
            update_response.json()["session"]["current_opening_framework"]["framework_summary"],
            "先定标准，再比较基础能力、教育公平与执行成本。",
        )

    def test_opening_brief_stream_endpoint(self) -> None:
        create_response = self.client.post(
            "/api/sessions",
            json={
                "topic": "人工智能是否应当被强制纳入高中通识教育",
                "user_side": "正方",
                "agent_side": "反方",
                "coach_feedback_mode": "manual",
                "web_search_enabled": True,
                "default_closing_side": "user",
            },
        )
        session_id = create_response.json()["session_id"]

        framework_response = self.client.post(
            f"/api/sessions/{session_id}/opening-framework/generate",
            json={"speaker_side": "user"},
        )
        framework = framework_response.json()["framework_result"]["framework"]

        with self.client.stream(
            "POST",
            f"/api/sessions/{session_id}/opening-briefs/stream",
            json={"speaker_side": "user", "target_duration_minutes": 3, "framework": framework},
        ) as response:
            self.assertEqual(response.status_code, 200)
            body = "".join(response.iter_text())

        self.assertIn("event: opening_chunk", body)
        self.assertIn("event: completed", body)
        self.assertNotIn("event: research_ready", body)

    def test_opening_brief_stream_requires_framework(self) -> None:
        create_response = self.client.post(
            "/api/sessions",
            json={
                "topic": "人工智能是否应当被强制纳入高中通识教育",
                "user_side": "正方",
                "agent_side": "反方",
                "coach_feedback_mode": "manual",
                "web_search_enabled": True,
                "default_closing_side": "user",
            },
        )
        session_id = create_response.json()["session_id"]

        with self.client.stream(
            "POST",
            f"/api/sessions/{session_id}/opening-briefs/stream",
            json={"speaker_side": "user", "target_duration_minutes": 3},
        ) as response:
            self.assertEqual(response.status_code, 200)
            body = "".join(response.iter_text())

        self.assertIn("event: error", body)
        self.assertIn("当前会话还没有可用框架稿", body)

    def test_opening_history_and_diff_endpoints(self) -> None:
        create_response = self.client.post(
            "/api/sessions",
            json={
                "topic": "人工智能是否应当被强制纳入高中通识教育",
                "user_side": "正方",
                "agent_side": "反方",
                "coach_feedback_mode": "manual",
                "web_search_enabled": True,
                "default_closing_side": "user",
            },
        )
        session_id = create_response.json()["session_id"]

        framework_payload = {
            "judge_standard": "比较哪一方更能稳定提升学生 AI 基础能力并控制资源挤出。",
            "framework_summary": "先定标准，再比较基础能力、教育公平与执行成本。",
            "argument_cards": [
                {
                    "claim": "AI 通识教育能补齐全体学生的基础识读能力。",
                    "data_support": "当前缺少可直接上场的硬证据。",
                    "academic_support": "通识教育的目标是建立跨专业的基本认知能力。",
                    "scenario_support": "学生面对 AI 生成内容时，若没有基础识读能力，就更容易误判信息。"
                }
            ]
        }
        first_import = self.client.post(
            f"/api/sessions/{session_id}/opening-briefs/import",
            json={
                "speaker_side": "user",
                "spoken_text": "各位评判，本题先比较哪一方更能补齐学生 AI 基础能力。",
                "framework": framework_payload,
                "target_duration_minutes": 3,
            },
        )
        first_brief_id = first_import.json()["opening_brief"]["brief_id"]
        self.client.post(f"/api/sessions/{session_id}/opening-briefs/coach")

        second_import = self.client.post(
            f"/api/sessions/{session_id}/opening-briefs/import",
            json={
                "speaker_side": "user",
                "spoken_text": "各位评判，本题应先比较哪一方更能补齐学生 AI 基础能力，并把资源挤出压到最低。",
                "framework": framework_payload,
                "target_duration_minutes": 3,
            },
        )
        second_brief_id = second_import.json()["opening_brief"]["brief_id"]
        self.client.post(f"/api/sessions/{session_id}/opening-briefs/coach")

        history_response = self.client.get(f"/api/sessions/{session_id}/opening/history")
        self.assertEqual(history_response.status_code, 200)
        history = history_response.json()["history"]
        self.assertEqual(len(history["briefs"]), 2)
        self.assertEqual(history["current_opening_brief_id"], second_brief_id)
        self.assertEqual(sum(1 for item in history["briefs"] if item["is_current"]), 1)

        diff_response = self.client.get(
            f"/api/sessions/{session_id}/opening-briefs/diff",
            params={"from_brief_id": first_brief_id, "to_brief_id": second_brief_id},
        )
        self.assertEqual(diff_response.status_code, 200)
        diff_payload = diff_response.json()["diff"]
        self.assertEqual(diff_payload["from_brief"]["brief_id"], first_brief_id)
        self.assertEqual(diff_payload["to_brief"]["brief_id"], second_brief_id)
        self.assertIn(first_brief_id, diff_payload["unified_diff"])
        self.assertIn("score_comparison", diff_payload)

    def test_evidence_workbench_endpoints(self) -> None:
        create_response = self.client.post(
            "/api/sessions",
            json={
                "topic": "人工智能是否应当被强制纳入高中通识教育",
                "user_side": "正方",
                "agent_side": "反方",
                "coach_feedback_mode": "manual",
                "web_search_enabled": True,
                "default_closing_side": "user",
            },
        )
        session_id = create_response.json()["session_id"]

        get_response = self.client.get(f"/api/sessions/{session_id}/evidence-workbench")
        self.assertEqual(get_response.status_code, 200)
        self.assertEqual(get_response.json()["evidence_workbench"]["session_id"], session_id)

        add_response = self.client.post(
            f"/api/sessions/{session_id}/evidence/user-supplied",
            json={
                "title": "地方试点课程数据",
                "source_ref": "manual://pilot-program",
                "snippet": "试点学校已把 AI 素养纳入信息技术课程，学生参与率持续提升。",
                "user_explanation": "用于证明课程推广已有现实基础。",
            },
        )
        self.assertEqual(add_response.status_code, 200)
        evidence_id = add_response.json()["evidence_workbench"]["user_supplied_evidence"][0]["evidence_id"]

        pin_response = self.client.post(
            f"/api/sessions/{session_id}/evidence/pin",
            json={"evidence_id": evidence_id},
        )
        self.assertEqual(pin_response.status_code, 200)
        self.assertEqual(pin_response.json()["evidence_workbench"]["pinned_evidence"][0]["evidence_id"], evidence_id)

        update_response = self.client.patch(
            f"/api/sessions/{session_id}/evidence/{evidence_id}/explanation",
            json={"user_explanation": "改为强调试点已经验证课程可执行。"},
        )
        self.assertEqual(update_response.status_code, 200)
        self.assertEqual(
            update_response.json()["evidence_workbench"]["user_supplied_evidence"][0]["user_explanation"],
            "改为强调试点已经验证课程可执行。",
        )

        blacklist_response = self.client.post(
            f"/api/sessions/{session_id}/evidence/blacklist-source-type",
            json={"source_type": "web_search"},
        )
        self.assertEqual(blacklist_response.status_code, 200)
        self.assertIn("web_search", blacklist_response.json()["evidence_workbench"]["blacklisted_source_types"])

        remove_response = self.client.delete(f"/api/sessions/{session_id}/evidence/blacklist-source-type/web_search")
        self.assertEqual(remove_response.status_code, 200)
        self.assertNotIn("web_search", remove_response.json()["evidence_workbench"]["blacklisted_source_types"])


if __name__ == "__main__":
    unittest.main()