from __future__ import annotations

from debate_agent.domain.models import DebatePhase, DebateProfile, DebateType


def create_demo_profile() -> DebateProfile:
    return DebateProfile(
        profile_id="policy-default",
        debate_type=DebateType.POLICY,
        judge_standard="比较方案净收益与可行性",
        burden_rules=["提出方案者需证明必要性与可行性", "反方需指出替代方案或核心缺陷"],
        preferred_attack_patterns=["机制攻击", "副作用攻击", "证明责任攻击"],
        preferred_question_patterns=["请你证明必要性", "请你解释执行路径"],
        evidence_policy=["只能引用可追溯资料", "证据不足时优先逻辑攻击"],
        style_constraints=["直接", "高压", "不绕弯"],
        phase_policies={
            DebatePhase.CROSSFIRE.value: {
                "response_length": "120-220字",
                "pressure_style": "高压短句",
            }
        },
    )
