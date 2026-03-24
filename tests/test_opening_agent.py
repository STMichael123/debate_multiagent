from __future__ import annotations

import unittest
from types import SimpleNamespace

from debate_agent.domain.models import DebatePhase, DebateSession, DebateType, DebateProfile, EvidenceRecord
from debate_agent.orchestration.agent_services import OpeningAgent
from debate_agent.prompts.builders import build_framework_axis_guidance, build_framework_card_requirements, build_opening_variables, build_topic_judge_standard_guidance


class FakeResponse:
    def __init__(self, model: str = "fake-model") -> None:
        self.model = model


class SequencedLLMClient:
    def __init__(self, payloads: list[dict[str, object]]) -> None:
        self.payloads = payloads
        self.calls = 0
        self.settings = SimpleNamespace()

    def parse_json(self, prompt: str, model: str | None = None) -> tuple[dict[str, object], FakeResponse]:
        payload = self.payloads[self.calls]
        self.calls += 1
        return payload, FakeResponse()


class OpeningAgentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.profile = DebateProfile(
            profile_id="test-profile",
            debate_type=DebateType.POLICY,
            judge_standard="比较哪一方更能证明自己的路径在必要性、可行性与净收益上成立。",
            burden_rules=["正方需证明方案必要且优于替代路径。"],
            preferred_attack_patterns=["证明责任攻击"],
            preferred_question_patterns=["追问替代方案"],
            evidence_policy=["不得编造来源"],
            style_constraints=["清晰成段"],
        )
        self.session = DebateSession(
            session_id="session-1",
            topic="人工智能是否应当被强制纳入高中通识教育",
            user_side="正方",
            agent_side="反方",
            profile_id=self.profile.profile_id,
            mode="crossfire",
            current_phase=DebatePhase.CROSSFIRE,
        )
        self.evidence_records = [
            EvidenceRecord(
                evidence_id="ev-1",
                query_text=self.session.topic,
                source_type="web_search_authoritative",
                source_ref="https://www.unesco.org/report",
                title="UNESCO education report",
                snippet="报告指出，系统性能力建设会显著影响学生在技术环境中的长期适应力。",
                credibility_score=0.9,
                relevance_score=0.88,
                verification_state="high_authority",
            )
        ]

    def test_retry_rejects_unstructured_opening_and_accepts_second_attempt(self) -> None:
        llm_client = SequencedLLMClient(
            payloads=[
                {
                    "judge_standard": "比较哪一方更能证明把人工智能纳入高中通识教育这项安排，能够在不过度挤占教育资源的前提下稳定提升目标能力，并改善教育公平。",
                    "framework_summary": "先锁判断标准，再用两个核心论点承接数据、学理和情景。",
                    "argument_cards": [
                        {
                            "claim": "系统纳入高中通识教育，能更稳定地补齐学生面对 AI 时代所需的基础识读能力。",
                            "data_support": "当前缺少可直接上场的硬证据。",
                            "academic_support": "制度主张必须说明为什么路径能够稳定实现目标。",
                            "scenario_support": "真实比赛里，评判会追问谁更完成了证明责任。",
                        },
                        {
                            "claim": "再说明本方路径为什么能稳定导向结果。",
                            "data_support": "UNESCO education report 指出，系统性能力建设会显著影响学生在技术环境中的长期适应力。",
                            "academic_support": "当资源配置不稳定时，能力差距会继续扩大。",
                            "scenario_support": "两个起点相近的学生会因为是否得到系统训练而逐渐拉开差距。",
                        },
                    ],
                    "evidence_citations": ["ev-1"],
                    "confidence_notes": [],
                },
                {
                    "strategy_summary": "空泛立论",
                    "outline": ["只讲态度"],
                    "spoken_text": "我方认为这件事很重要，所以应该支持。",
                    "evidence_citations": [],
                    "confidence_notes": [],
                },
                {
                    "strategy_summary": "按强结构输出一辩稿。",
                    "outline": ["判断标准", "证据位", "学理链", "生活情景", "证明责任"],
                    "spoken_text": (
                        "各位评判，今天这道题要比较的是哪一方更能完成必要性、可行性和净收益的证明。"
                        "本方先锁住判断标准：谁更能证明自己的路径稳定成立，谁就更接近胜出。"
                        "第一，我们说明为什么评判必须从必要性与可行性出发，而不能只看愿景是否动听。"
                        "第二，根据 UNESCO education report 的资料，系统性能力建设会显著影响学生在技术环境中的长期适应力，"
                        "这说明相关能力如果只留给个体零散补足，真实结果往往不是普遍提升，而是机会继续分化。"
                        "第三，从机制上看，当教育配置缺乏稳定入口时，资源只会沿着家庭支持、学校条件和信息差继续分配，"
                        "最后把本可以被提前修补的差距固化下来。"
                        "放进生活场景里看，两个起点相近的学生，一个在学校里能稳定接受相关训练，另一个只能在课余自己摸索，"
                        "短期看两人都还有选择，但一旦进入真正需要使用这类能力的升学和社会场景，后者就会持续在理解成本和试错成本上落后。"
                        "所以本方今天的核心赢点就在于，我们证明了为什么这件事不能只靠零散自觉，而需要稳定配置，也把对方逼回证明责任。"
                        "回到判断标准再看，这场比赛真正要比较的不是谁先喊出目标更好，而是谁能说明自己的路径为什么更稳定、为什么更可执行、为什么能覆盖到真实人群。"
                        "如果对方不能回答在缺少稳定配置的情况下，他们如何避免机会差、能力差和信息差继续被放大，那么他们就没有完成必要性和可行性的证明。"
                        "而本方之所以占优，不是因为我们更会描述理想未来，而是因为我们已经把判断标准、证据支点、学理机制和现实场景连成了一条完整链条。"
                    ),
                    "evidence_citations": ["ev-1"],
                    "confidence_notes": [],
                },
            ]
        )
        agent = OpeningAgent(llm_client=llm_client)

        result = agent.generate(
            session=self.session,
            profile=self.profile,
            evidence_records=self.evidence_records,
            speaker_side="正方",
            brief_focus="建立完整一辩稿骨架。",
            target_duration_minutes=3,
        )

        self.assertEqual(llm_client.calls, 3)
        self.assertEqual(result.opening_brief.evidence_citations, [])
        self.assertIsNotNone(result.opening_brief.framework)
        assert result.opening_brief.framework is not None
        self.assertEqual(result.opening_brief.target_duration_minutes, 3)
        self.assertGreaterEqual(len(result.opening_brief.framework.argument_cards), 2)
        self.assertNotEqual(result.opening_brief.framework.judge_standard, self.profile.judge_standard)
        self.assertIn("[Retry Instruction]", result.prompt)

    def test_fallback_opening_contains_mechanism_and_concrete_scenario(self) -> None:
        agent = OpeningAgent(llm_client=None)

        result = agent.generate(
            session=self.session,
            profile=self.profile,
            evidence_records=[],
            speaker_side="正方",
            brief_focus="建立完整一辩稿骨架。",
            target_duration_minutes=4,
        )

        text = result.opening_brief.spoken_text
        self.assertIsNotNone(result.opening_brief.framework)
        assert result.opening_brief.framework is not None
        self.assertGreaterEqual(len(result.opening_brief.framework.argument_cards), 2)
        self.assertIn("机制", text)
        self.assertIn("试想", text)
        self.assertIn("缺少", text)
        self.assertEqual(result.opening_brief.target_duration_minutes, 4)
        self.assertEqual(result.opening_brief.target_word_count, 1200)
        self.assertIn("教育", result.opening_brief.framework.judge_standard)

    def test_fallback_judge_standard_changes_with_topic(self) -> None:
        session = DebateSession(
            session_id="session-2",
            topic="短视频平台是否应加强未成年人使用限制",
            user_side="正方",
            agent_side="反方",
            profile_id=self.profile.profile_id,
            mode="crossfire",
            current_phase=DebatePhase.CROSSFIRE,
        )
        agent = OpeningAgent(llm_client=None)

        result = agent.generate(
            session=session,
            profile=self.profile,
            evidence_records=[],
            speaker_side="正方",
            brief_focus="建立完整一辩稿骨架。",
            target_duration_minutes=3,
        )

        assert result.opening_brief.framework is not None
        judge_standard = result.opening_brief.framework.judge_standard
        self.assertIn("未成年人", judge_standard)
        self.assertIn("误伤", judge_standard)

    def test_memory_responsibility_topic_gets_specialized_framework_guidance(self) -> None:
        session = DebateSession(
            session_id="session-3",
            topic="彻底失去记忆后的全新人生不该对之前犯下的罪行负责",
            user_side="反方",
            agent_side="正方",
            profile_id=self.profile.profile_id,
            mode="crossfire",
            current_phase=DebatePhase.CROSSFIRE,
        )

        opening_variables = build_opening_variables(
            session=session,
            profile=self.profile,
            evidence_records=[],
            speaker_side="反方",
            brief_focus="先搭建反方完整框架稿。",
            target_duration_minutes=3,
        )

        judge_guidance = build_topic_judge_standard_guidance(session.topic, self.profile)
        axis_guidance = build_framework_axis_guidance(session.topic, self.profile)
        card_requirements = build_framework_card_requirements(session.topic, self.profile)

        self.assertIn("责任应归属于什么主体", judge_guidance)
        self.assertIn("规范基础是否仍成立", judge_guidance)
        self.assertIn("主体连续性", axis_guidance)
        self.assertIn("规范正当性", axis_guidance)
        self.assertIn("身份变化", card_requirements)
        self.assertIn("scenario_support 是必备字段", card_requirements)
        self.assertIn("framework_axis_guidance", opening_variables)
        self.assertIn("framework_card_requirements", opening_variables)

    def test_memory_responsibility_topic_fallback_judge_standard_is_specialized(self) -> None:
        session = DebateSession(
            session_id="session-4",
            topic="彻底失去记忆后的全新人生不该对之前犯下的罪行负责",
            user_side="反方",
            agent_side="正方",
            profile_id=self.profile.profile_id,
            mode="crossfire",
            current_phase=DebatePhase.CROSSFIRE,
        )
        agent = OpeningAgent(llm_client=None)

        result = agent.generate(
            session=session,
            profile=self.profile,
            evidence_records=[],
            speaker_side="反方",
            brief_focus="先搭建反方完整框架稿。",
            target_duration_minutes=3,
        )

        assert result.opening_brief.framework is not None
        judge_standard = result.opening_brief.framework.judge_standard
        self.assertIn("主体连续性", judge_standard)
        self.assertIn("规范正当性", judge_standard)
        self.assertIn("社会后果", judge_standard)

    def test_new_energy_vehicle_topic_gets_specialized_framework_guidance(self) -> None:
        session = DebateSession(
            session_id="session-5",
            topic="安徽的新能源汽车的整车规模还是零部件发展更紧迫",
            user_side="正方",
            agent_side="反方",
            profile_id=self.profile.profile_id,
            mode="crossfire",
            current_phase=DebatePhase.CROSSFIRE,
        )

        opening_variables = build_opening_variables(
            session=session,
            profile=self.profile,
            evidence_records=[],
            speaker_side="正方",
            brief_focus="先搭建产业题框架稿。",
            target_duration_minutes=3,
        )

        judge_guidance = build_topic_judge_standard_guidance(session.topic, self.profile)
        axis_guidance = build_framework_axis_guidance(session.topic, self.profile)
        card_requirements = build_framework_card_requirements(session.topic, self.profile)

        self.assertIn("关键瓶颈", judge_guidance)
        self.assertIn("长期健康发展", judge_guidance)
        self.assertIn("结构性瓶颈", axis_guidance)
        self.assertIn("核心能力约束", axis_guidance)
        self.assertIn("利润率", card_requirements)
        self.assertIn("规模扩张但利润下滑", card_requirements)
        self.assertIn("framework_axis_guidance", opening_variables)
        self.assertIn("framework_card_requirements", opening_variables)

    def test_new_energy_vehicle_topic_fallback_judge_standard_is_specialized(self) -> None:
        session = DebateSession(
            session_id="session-6",
            topic="安徽的新能源汽车的整车规模还是零部件发展更紧迫",
            user_side="正方",
            agent_side="反方",
            profile_id=self.profile.profile_id,
            mode="crossfire",
            current_phase=DebatePhase.CROSSFIRE,
        )
        agent = OpeningAgent(llm_client=None)

        result = agent.generate(
            session=session,
            profile=self.profile,
            evidence_records=[],
            speaker_side="正方",
            brief_focus="先搭建产业题框架稿。",
            target_duration_minutes=3,
        )

        assert result.opening_brief.framework is not None
        judge_standard = result.opening_brief.framework.judge_standard
        self.assertIn("关键约束", judge_standard)
        self.assertIn("价值链位置", judge_standard)
        self.assertIn("长期韧性", judge_standard)


if __name__ == "__main__":
    unittest.main()
