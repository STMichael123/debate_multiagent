from __future__ import annotations

import re

from debate_agent.domain.models import AgentOutput, ClashPoint, DebateProfile, DebateSession, EvidenceRecord, OpeningBrief, OpeningFramework, PreparationPacket


def format_clash_points(clash_points: list[ClashPoint]) -> str:
    if not clash_points:
        return "当前尚未形成稳定 clash。"

    lines: list[str] = []
    for index, clash in enumerate(clash_points, start=1):
        lines.append(f"争议点 {index}：{clash.summary}")
        if clash.open_questions:
            lines.append(f"待追问：{'；'.join(clash.open_questions)}")
    return "\n".join(lines)


def format_evidence_packet(evidence_records: list[EvidenceRecord]) -> str:
    if not evidence_records:
        return "当前没有可用证据，请优先进行逻辑攻击与证明责任攻击。"

    grouped: dict[str, list[EvidenceRecord]] = {
        "具体数据": [],
        "学理研究": [],
        "情景推演": [],
    }
    for evidence in evidence_records:
        grouped[_classify_evidence_strength(evidence)].append(evidence)

    lines: list[str] = []
    lines.append("举证效力排序：具体数据 > 学理研究 > 情景推演。应优先使用更高位阶的材料支撑判断。")
    for label in ["具体数据", "学理研究", "情景推演"]:
        bucket = grouped[label]
        if not bucket:
            continue
        lines.append(f"[{label}]")
        for evidence in bucket:
            credibility = f"{evidence.credibility_score:.2f}" if evidence.credibility_score is not None else "未知"
            relevance = f"{evidence.relevance_score:.2f}" if evidence.relevance_score is not None else "未知"
            source_tier = _classify_source_authority(evidence)
            note = f"；用户备注={evidence.user_explanation}" if evidence.user_explanation else ""
            pinned = "；状态=已钉住" if evidence.is_pinned else ""
            lines.append(
                f"{evidence.evidence_id}: 标题={evidence.title}；来源={evidence.source_ref}；"
                f"摘要={evidence.snippet}；来源位阶={source_tier}；相关性={relevance}；可信度={credibility}；校验状态={evidence.verification_state}{pinned}{note}"
            )
    return "\n".join(lines)


def build_evidence_usage_guidance(evidence_records: list[EvidenceRecord]) -> str:
    if not evidence_records:
        return (
            "当前无高质量证据可用。不要捏造数字，不要假装存在某份研究。"
            "你必须改用学理机制和生活情景两段式组织："
            "先解释这道题为什么在定义、机制或制度逻辑上成立，再给出一个贴近日常决策的具体场景帮助评判理解影响。"
        )
    return (
        "只有具备官方机构、学术研究、权威组织报告或可信原始报道属性的网页，才能作为硬证据引用。"
        "来自辩论稿转载、论坛问答、自媒体二次转述、资料汇编页的内容，一律不得当作权威数据来源。"
        "举证效力规则：第一优先使用可量化的具体数据、统计、比例、样本或明确事实；"
        "第二优先使用研究结论、学者观点、报告框架和学理归纳；"
        "第三才使用基于生活经验构建的情景推演。"
        "如果高位阶证据已经足够，就不要用低位阶情景替代。"
        "如果缺少合格数据，你必须明确转入学理路径：先界定核心机制，再说明因果链条，再解释为什么这条链条足以支持本方判断。"
        "如果连成熟学理也不充分，再转入生活情景路径：构造一个具体、可感、贴近普通人经验的场景，说明政策或价值选择将如何影响真实人的选择与处境，但不得把情景包装成统计事实。"
    )


def build_evidence_quality_summary(evidence_records: list[EvidenceRecord]) -> str:
    if not evidence_records:
        return "当前没有任何可直接引用的网页或资料。"
    summary = {
        "高效力数据": 0,
        "可用学理": 0,
        "仅情景支持": 0,
    }
    for evidence in evidence_records:
        bucket = _classify_evidence_strength(evidence)
        authority = _classify_source_authority(evidence)
        if bucket == "具体数据" and authority in {"高", "中高"}:
            summary["高效力数据"] += 1
        elif bucket == "学理研究" and authority in {"高", "中高", "中"}:
            summary["可用学理"] += 1
        else:
            summary["仅情景支持"] += 1
    return "；".join(f"{key}={value}" for key, value in summary.items())


def build_base_prompt_variables(
    session: DebateSession,
    profile: DebateProfile,
    recent_turns_summary: str,
    active_clash_points: list[ClashPoint],
    evidence_records: list[EvidenceRecord],
) -> dict[str, str]:
    phase_policy = profile.phase_policies.get(session.current_phase.value, {})
    opening_brief = _resolve_current_opening_brief(session)
    preparation_packet = session.preparation_packets[-1] if session.preparation_packets else None
    return {
        "topic": session.topic,
        "debate_type": profile.debate_type.value,
        "judge_standard": profile.judge_standard,
        "burden_rules": "；".join(profile.burden_rules),
        "preferred_attack_patterns": "；".join(profile.preferred_attack_patterns),
        "preferred_question_patterns": "；".join(profile.preferred_question_patterns),
        "evidence_policy": "；".join(profile.evidence_policy),
        "style_constraints": "；".join(profile.style_constraints),
        "current_phase": session.current_phase.value,
        "response_length": phase_policy.get("response_length", "120-220字"),
        "pressure_style": phase_policy.get("pressure_style", "高压短句"),
        "user_side": session.user_side,
        "agent_side": session.agent_side,
        "recent_turns_summary": recent_turns_summary or session.context_summary or "暂无历史摘要。",
        "active_clash_points": format_clash_points(active_clash_points),
        "evidence_packet": format_evidence_packet(evidence_records),
        "opening_brief_packet": format_opening_brief_packet(opening_brief),
        "preparation_packet": format_preparation_packet(preparation_packet),
        "preparation_opening_hint": preparation_packet.recommended_opening_frame if preparation_packet is not None else "当前没有备赛阶段提供的开篇建议。",
    }


def build_opponent_variables(
    session: DebateSession,
    profile: DebateProfile,
    recent_turns_summary: str,
    active_clash_points: list[ClashPoint],
    pending_response_arguments: str,
    target_argument_ids: list[str],
    evidence_records: list[EvidenceRecord],
) -> dict[str, str]:
    variables = build_base_prompt_variables(
        session=session,
        profile=profile,
        recent_turns_summary=recent_turns_summary,
        active_clash_points=active_clash_points,
        evidence_records=evidence_records,
    )
    variables.update(
        {
            "pending_response_arguments": pending_response_arguments or "暂无待回应点。",
            "target_argument_ids": "、".join(target_argument_ids) or "未显式指定",
            "latest_user_turn": "",
            "latest_opponent_turn": "",
        }
    )
    return variables


def build_coach_variables(
    session: DebateSession,
    profile: DebateProfile,
    recent_turns_summary: str,
    active_clash_points: list[ClashPoint],
    evidence_records: list[EvidenceRecord],
    latest_user_turn: str,
    latest_opponent_turn: str,
) -> dict[str, str]:
    coach_variables = build_base_prompt_variables(
        session=session,
        profile=profile,
        recent_turns_summary=recent_turns_summary,
        active_clash_points=active_clash_points,
        evidence_records=evidence_records,
    )
    coach_variables["latest_user_turn"] = latest_user_turn
    coach_variables["latest_opponent_turn"] = latest_opponent_turn
    return coach_variables


def build_closing_variables(
    session: DebateSession,
    profile: DebateProfile,
    recent_turns_summary: str,
    active_clash_points: list[ClashPoint],
    evidence_records: list[EvidenceRecord],
    speaker_side: str,
    closing_focus: str,
) -> dict[str, str]:
    closing_variables = build_base_prompt_variables(
        session=session,
        profile=profile,
        recent_turns_summary=recent_turns_summary,
        active_clash_points=active_clash_points,
        evidence_records=evidence_records,
    )
    closing_variables["speaker_side"] = speaker_side
    closing_variables["closing_focus"] = closing_focus
    closing_variables["closing_length"] = "600-900字"
    closing_variables["evidence_usage_guidance"] = build_evidence_usage_guidance(evidence_records)
    closing_variables["evidence_quality_summary"] = build_evidence_quality_summary(evidence_records)
    return closing_variables


def build_opening_variables(
    session: DebateSession,
    profile: DebateProfile,
    evidence_records: list[EvidenceRecord],
    speaker_side: str,
    brief_focus: str,
    target_duration_minutes: int,
) -> dict[str, str]:
    opening_variables = build_base_prompt_variables(
        session=session,
        profile=profile,
        recent_turns_summary=session.context_summary,
        active_clash_points=session.clash_points,
        evidence_records=evidence_records,
    )
    opening_variables["speaker_side"] = speaker_side
    opening_variables["brief_focus"] = brief_focus
    opening_variables["target_duration_minutes"] = str(target_duration_minutes)
    opening_variables["opening_length"] = f"{target_duration_minutes * 300}-{target_duration_minutes * 320}字"
    opening_variables["evidence_usage_guidance"] = build_evidence_usage_guidance(evidence_records)
    opening_variables["evidence_quality_summary"] = build_evidence_quality_summary(evidence_records)
    opening_variables["macro_judge_standard"] = profile.judge_standard
    opening_variables["topic_judge_standard_guidance"] = build_topic_judge_standard_guidance(session.topic, profile)
    opening_variables["framework_axis_guidance"] = build_framework_axis_guidance(session.topic, profile)
    opening_variables["framework_card_requirements"] = build_framework_card_requirements(session.topic, profile)
    return opening_variables


def format_opening_framework_packet(framework: OpeningFramework | None) -> str:
    if framework is None:
        return "当前没有可用框架稿。"

    lines = [
        f"判断标准：{framework.judge_standard or '未明确'}",
        f"框架摘要：{framework.framework_summary or '未明确'}",
    ]
    for index, card in enumerate(framework.argument_cards, start=1):
        lines.append(f"论点 {index} 内容：{card.claim or '未明确'}")
        lines.append(f"数据填充：{card.data_support or '未补'}")
        lines.append(f"学理填充：{card.academic_support or '未补'}")
        lines.append(f"情景填充：{card.scenario_support or '未补'}")
    return "\n".join(lines)


def build_opening_draft_variables(
    session: DebateSession,
    profile: DebateProfile,
    speaker_side: str,
    brief_focus: str,
    target_duration_minutes: int,
    framework: OpeningFramework,
) -> dict[str, str]:
    preparation_packet = session.preparation_packets[-1] if session.preparation_packets else None
    variables = {
        "topic": session.topic,
        "speaker_side": speaker_side,
        "debate_type": profile.debate_type.value,
        "brief_focus": brief_focus,
        "target_duration_minutes": str(target_duration_minutes),
        "opening_length": f"{target_duration_minutes * 300}-{target_duration_minutes * 320}字",
        "preparation_packet": format_preparation_packet(preparation_packet),
        "preparation_opening_hint": preparation_packet.recommended_opening_frame if preparation_packet is not None else "当前没有备赛阶段提供的开篇建议。",
    }
    variables["framework_judge_standard"] = framework.judge_standard or profile.judge_standard
    variables["framework_summary"] = framework.framework_summary or "未提供框架摘要。"
    variables["framework_packet"] = format_opening_framework_packet(framework)
    return variables


def build_opening_coach_variables(
    session: DebateSession,
    profile: DebateProfile,
    evidence_records: list[EvidenceRecord],
    opening_brief: OpeningBrief,
) -> dict[str, str]:
    coach_variables = build_base_prompt_variables(
        session=session,
        profile=profile,
        recent_turns_summary=session.context_summary,
        active_clash_points=session.clash_points,
        evidence_records=evidence_records,
    )
    coach_variables["speaker_side"] = opening_brief.speaker_side
    coach_variables["opening_brief_text"] = opening_brief.spoken_text
    coach_variables["opening_brief_outline"] = "；".join(opening_brief.outline) or "暂无提纲"
    coach_variables["opening_brief_strategy"] = opening_brief.strategy_summary
    return coach_variables


def build_topic_judge_standard_guidance(topic: str, profile: DebateProfile) -> str:
    normalized_topic = topic.strip()
    lower_topic = normalized_topic.lower()
    guidance_parts: list[str] = []

    if profile.debate_type.value == "policy":
        guidance_parts.append("先识别这道题到底在比较什么行动路径、由谁执行、作用于谁，再据此确定判断标准。")
        guidance_parts.append("本题判断标准不能直接照抄通用的‘净收益与可行性’，而应具体回答：哪一方更能证明这项具体安排为何必要、如何落地、代价落在谁身上。")
    elif profile.debate_type.value == "value":
        guidance_parts.append("先识别这道题冲突的核心价值是什么，再判断哪一方更能证明自己保护了优先价值且代价更小。")
    else:
        guidance_parts.append("先识别本题到底在争什么事实判断，再比较哪一方证据质量更高、解释力更强、反例更少。")

    if any(keyword in normalized_topic for keyword in ["教育", "学校", "课程", "高中", "大学", "学生"]):
        guidance_parts.append("如果辩题涉及教育配置，判断标准应聚焦：这项安排能否稳定提升目标能力、是否挤占关键教育资源、会不会扩大或缩小教育公平差距。")
    if any(keyword in normalized_topic for keyword in ["未成年人", "儿童", "青少年"]):
        guidance_parts.append("如果辩题涉及未成年人，判断标准应聚焦：谁更能在保护未成年人核心利益的同时，把误伤和治理副作用压到更低。")
    if any(keyword in normalized_topic for keyword in ["记忆", "失忆", "人格", "责任", "罪行", "罪责", "刑罚", "谴责", "自责", "法律"]):
        guidance_parts.append("如果辩题涉及身份连续性、责任归属或法律追责，判断标准不能只停留在情绪直觉，而要比较：责任应归属于什么主体、规范基础是否仍成立、这种处理方式会带来什么更广泛的后果。")
        guidance_parts.append("这类题目的 judge_standard 最好写成多维比较结构，例如：谁更能在主体连续性、规范正当性与社会后果三个维度上完成论证，谁就更成立。")
    if any(keyword in normalized_topic for keyword in ["平台", "监管", "限制", "治理", "封禁", "审查"]):
        guidance_parts.append("如果辩题涉及平台治理或限制措施，判断标准应聚焦：措施是否精准有效、边界是否清晰、执行成本是否可控、误伤是否更少。")
    if any(keyword in normalized_topic for keyword in ["汽车", "新能源", "整车", "零部件", "芯片", "电机", "产业链", "制造业", "供应链"]):
        guidance_parts.append("如果辩题涉及制造业、产业链或产业升级，判断标准不能只看规模扩张，而要比较：谁更能识别并解决关键瓶颈、提升价值链位置、增强长期韧性。")
        guidance_parts.append("这类题目的 judge_standard 最好直接落到‘谁更能解决当前发展中的关键约束并支撑长期健康发展’这一层，而不是泛泛比较谁更重要。")
    if any(keyword in normalized_topic for keyword in ["自由", "权利", "隐私", "表达", "言论", "自主"]):
        guidance_parts.append("如果辩题涉及权利或自由，判断标准应聚焦：公共目标是否足以支持限制、限制是否必要且比例适当、有没有更小侵害的替代路径。")
    if any(keyword in lower_topic for keyword in ["市场", "企业", "经济", "就业", "产业", "效率"]):
        guidance_parts.append("如果辩题涉及市场或经济后果，判断标准应聚焦：激励是否更健康、效率是否更高、长期结构后果是否更优。")

    guidance_parts.append(f"辩题原文：{normalized_topic or '未提供辩题'}。你输出的 judge_standard 必须让评判一眼看出，这个标准就是为这道题量身定制的。")
    return "\n".join(guidance_parts)


def build_framework_axis_guidance(topic: str, profile: DebateProfile) -> str:
    normalized_topic = topic.strip()
    guidance_parts: list[str] = [
        "框架稿不是素材堆积，而是比较结构。你需要先决定这道题最值得比较的 2 到 3 条轴线，再据此安排 argument_cards。",
        "argument_cards 之间必须彼此区分：可以分别处理哲学基础、法律后果、社会影响，或分别处理必要性、正当性、后果与执行。",
        "每个论点都应自然预埋攻防：既说明本方为什么成立，也让对方必须回应一个无法绕开的证明责任缺口。",
    ]

    if any(keyword in normalized_topic for keyword in ["记忆", "失忆", "人格", "责任", "罪行", "罪责", "刑罚", "谴责", "自责", "法律"]):
        guidance_parts.append("对于责任归属类辩题，优先考虑这三条比较轴：第一，承担责任的主体是否连续；第二，追责或免责的规范基础是否成立；第三，这种处理方式会导向怎样的社会后果。")
        guidance_parts.append("如果你采用三条轴线，三张 argument_card 可以分别承载：主体连续性、规范正当性、社会影响。")
    elif any(keyword in normalized_topic for keyword in ["汽车", "新能源", "整车", "零部件", "芯片", "电机", "产业链", "制造业", "供应链"]):
        guidance_parts.append("对于产业升级类辩题，优先考虑这三条比较轴：第一，当前关键约束到底落在规模端、价值链端还是核心能力端；第二，哪条路径更能解决利润、技术或安全边际问题；第三，哪条路径更能支撑长期升级而非短期冲量。")
        guidance_parts.append("如果你采用三条轴线，三张 argument_card 可以分别承载：结构性瓶颈、核心能力约束、长期升级路径。")
    elif profile.debate_type.value == "policy":
        guidance_parts.append("对于政策题，优先把论点拆成‘为什么必要’、‘为什么可行’、‘为什么整体后果更优’三层。")
    elif profile.debate_type.value == "value":
        guidance_parts.append("对于价值题，优先把论点拆成‘为什么本方保护更优先的价值’、‘为什么对方代价更大’、‘为什么本方路径更可被普遍接受’三层。")
    else:
        guidance_parts.append("对于事实题，优先把论点拆成‘证据质量’、‘解释力’、‘对反例的回应能力’三层。")

    return "\n".join(guidance_parts)


def build_framework_card_requirements(topic: str, profile: DebateProfile) -> str:
    normalized_topic = topic.strip()
    requirements = [
        "claim 必须写成完整判断句，直接回答‘在当前判准下，本方到底证明了什么’。",
        "data_support 能给硬数据就给硬数据；没有就老实承认证据缺口，但不能留空。",
        "academic_support 必须讲清楚机制、法理或理论链条，不能只写抽象价值判断。",
        "scenario_support 是必备字段，必须给出一个具体、可感、能帮助评判理解后果的生活或制度场景。",
        "每个论点最后都要能自然导向一句潜台词：如果对方要反驳，他必须回应什么。即便这句话不单独写成字段，claim 和支撑也要把这个口子留出来。",
    ]

    if any(keyword in normalized_topic for keyword in ["记忆", "失忆", "人格", "责任", "罪行", "罪责", "刑罚", "谴责", "自责", "法律"]):
        requirements.append("在责任归属类辩题中，scenario_support 不要只写抽象伦理话术，应优先用身份变化、认知能力变化、极端人格断裂或边缘司法场景帮助解释责任归属为何变化。")
        requirements.append("在责任归属类辩题中，academic_support 应优先寻找主体连续性、可归责性、规范目的、正当化基础等理论抓手。")
    if any(keyword in normalized_topic for keyword in ["汽车", "新能源", "整车", "零部件", "芯片", "电机", "产业链", "制造业", "供应链"]):
        requirements.append("在产业升级类辩题中，claim 最好直接写成‘当前发展瓶颈是什么，以及为什么本方路径更能解决这个关键约束’。")
        requirements.append("在产业升级类辩题中，data_support 应优先放利润率、产能利用率、价值链占比、进口依赖度、市场集中度、研发投入等结构性数据。")
        requirements.append("在产业升级类辩题中，academic_support 应优先解释高附加值环节、产业链控制力、技术壁垒、价值链分布与供应链安全。")
        requirements.append("在产业升级类辩题中，scenario_support 应优先落到企业亏损、关键环节受制于人、规模扩张但利润下滑、核心能力不足导致发展受阻等真实产业场景。")

    if profile.debate_type.value == "policy":
        requirements.append("政策题的情景最好落到谁执行、谁承担成本、谁真正受影响，而不是只写社会会更好。")

    return "\n".join(requirements)


def _classify_evidence_strength(evidence: EvidenceRecord) -> str:
    text = " ".join([evidence.title, evidence.snippet, evidence.source_ref, evidence.source_type]).lower()
    if _looks_like_concrete_data(text):
        return "具体数据"
    if _looks_like_academic_reasoning(text):
        return "学理研究"
    return "情景推演"


def _looks_like_concrete_data(text: str) -> bool:
    data_keywords = ["数据", "统计", "样本", "比例", "percent", "%", "survey", "poll", "rate", "increase", "decrease"]
    has_number = bool(re.search(r"\d", text))
    return has_number or any(keyword in text for keyword in data_keywords)


def _looks_like_academic_reasoning(text: str) -> bool:
    academic_keywords = [
        "研究",
        "报告",
        "论文",
        "学者",
        "期刊",
        "理论",
        "文献",
        "大学",
        "研究院",
        "study",
        "research",
        "journal",
        "paper",
        "theory",
        "university",
        "report",
    ]
    return any(keyword in text for keyword in academic_keywords)


def _classify_source_authority(evidence: EvidenceRecord) -> str:
    credibility = evidence.credibility_score if evidence.credibility_score is not None else 0.0
    if credibility >= 0.8:
        return "高"
    if credibility >= 0.65:
        return "中高"
    if credibility >= 0.5:
        return "中"
    return "低"


def build_opponent_preview(agent_output: AgentOutput) -> str:
    lines = [
        f"攻击目标: {'、'.join(agent_output.rebuttal_target_ids) if agent_output.rebuttal_target_ids else '未指定'}",
        f"攻击路径: {agent_output.attack_strategy}",
        "输出提纲:",
    ]
    lines.extend(f"- {item}" for item in agent_output.response_outline)
    lines.append("正式发言:")
    lines.append(agent_output.spoken_text)
    lines.append("追问:")
    lines.extend(f"- {item}" for item in agent_output.follow_up_questions)
    return "\n".join(lines)


def build_session_state_preview(session: DebateSession) -> str:
    lines = [
        f"回合数: {len(session.turns)}",
        f"累计论点数: {len(session.arguments)}",
        f"累计 clash 数: {len(session.clash_points)}",
        f"教练模式: {session.options.coach_feedback_mode.value}",
        f"网页检索: {'开启' if session.options.web_search_enabled else '关闭'}",
        f"已生成陈词数: {len(session.closing_outputs)}",
        f"当前活跃 clash: {'、'.join(session.active_clash_point_ids) if session.active_clash_point_ids else '无'}",
        f"待回应论点: {'、'.join(session.pending_response_argument_ids) if session.pending_response_argument_ids else '无'}",
        f"上下文摘要: {session.context_summary or '无'}",
    ]
    return "\n".join(lines)


def format_opening_brief_packet(opening_brief: OpeningBrief | None) -> str:
    if opening_brief is None or not opening_brief.spoken_text.strip():
        return "当前尚未确定一辩稿骨架。"
    outline = "；".join(opening_brief.outline) if opening_brief.outline else "暂无提纲"
    return (
        f"当前一辩稿立场={opening_brief.speaker_side}；来源模式={opening_brief.source_mode}；"
        f"策略摘要={opening_brief.strategy_summary}；提纲={outline}；"
        f"正文={opening_brief.spoken_text}"
    )


def format_preparation_packet(preparation_packet: PreparationPacket | None) -> str:
    if preparation_packet is None:
        return "当前没有可复用的备赛资料包。"

    evidence_titles = "；".join(record.title for record in preparation_packet.evidence_records[:3] if record.title) or "暂无资料标题"
    theory_lines = []
    for theory_point in preparation_packet.theory_points[:3]:
        source_ids = "、".join(theory_point.source_evidence_ids) or "无显式证据编号"
        theory_lines.append(
            f"{theory_point.label}: 机制={theory_point.mechanism}；辩论价值={theory_point.debate_value or '未补'}；来源={source_ids}"
        )
    theory_summary = "\n".join(theory_lines) or "当前没有学理抓手。"
    argument_seeds = "；".join(preparation_packet.argument_seeds[:3]) or "暂无论点种子。"
    counterplay_risks = "；".join(preparation_packet.counterplay_risks[:3]) or "暂无显式风险提醒。"
    return (
        f"备赛检索查询={preparation_packet.research_query or '未记录'}\n"
        f"备赛资料预览={evidence_titles}\n"
        f"学理抓手：\n{theory_summary}\n"
        f"论点种子={argument_seeds}\n"
        f"风险提示={counterplay_risks}\n"
        f"推荐开篇方向={preparation_packet.recommended_opening_frame or '未提供'}"
    )


def _resolve_current_opening_brief(session: DebateSession) -> OpeningBrief | None:
    if session.current_opening_brief_id:
        for opening_brief in reversed(session.opening_briefs):
            if opening_brief.brief_id == session.current_opening_brief_id:
                return opening_brief
    if not session.opening_briefs:
        return None
    return session.opening_briefs[-1]


def format_reference_examples(examples: list) -> str:
    """Format benchmark examples for few-shot injection into prompts.

    Accepts a list of DebateExample objects from the ExampleBank.
    Returns a formatted string for the [Reference Examples] prompt section.
    """
    if not examples:
        return ""

    sections: list[str] = []
    for index, example in enumerate(examples, start=1):
        lines = [f"【示例 {index}】"]

        # Speaker context
        role_label = "正方" if example.side == "affirmative" else "反方"
        lines.append(f"辩手：{example.speaker_label or role_label}")
        lines.append(f"辩题：{example.topic}")
        lines.append(f"阶段：{example.phase}")

        # Raw text
        if example.raw_excerpt:
            excerpt_preview = example.raw_excerpt[:300]
            if len(example.raw_excerpt) > 300:
                excerpt_preview += "…"
            lines.append(f"原话片段：{excerpt_preview}")

        # Argument annotations
        if example.arguments:
            for arg_index, arg in enumerate(example.arguments[:3], start=1):
                arg_lines = [f"论证 {arg_index}："]
                if arg.claim:
                    arg_lines.append(f"  Claim（主张）：{arg.claim}")
                if arg.warrant:
                    arg_lines.append(f"  Warrant（依据）：{arg.warrant}")
                if arg.impact:
                    arg_lines.append(f"  Impact（影响）：{arg.impact}")
                if arg.tags:
                    arg_lines.append(f"  标签：{'、'.join(arg.tags)}")
                lines.append("\n".join(arg_lines))

        # Attack pattern
        if example.attack_type:
            attack_labels = {
                "definition_challenge": "定义攻击 — 重新界定核心概念",
                "causal_challenge": "因果攻击 — 质疑因果链条",
                "threshold_challenge": "门槛攻击 — 质疑标准是否达到",
                "framing_challenge": "框架攻击 — 重塑讨论框架",
                "logical_challenge": "逻辑攻击 — 指出推理漏洞",
                "impact_challenge": "影响攻击 — 削弱或翻转后果",
            }
            label = attack_labels.get(example.attack_type, example.attack_type)
            lines.append(f"攻击策略：{label}")

        # Claim role
        if example.claim_role:
            role_labels = {
                "setup": "铺垫 — 为后续论证建立前提",
                "offense": "进攻 — 主动提出主张",
                "rebuttal": "反驳 — 回应对方论点",
                "weighing": "权衡 — 比较双方论点的重要性",
            }
            role_text = role_labels.get(example.claim_role, example.claim_role)
            lines.append(f"角色：{role_text}")

        sections.append("\n".join(lines))

    header = (
        "以下摘自真实高水平辩赛的结构化标注，供你学习论证深度、攻击策略和表达风格：\n"
        "请注意这些示例的论证结构（claim → warrant → impact 的清晰链条）、"
        "攻击的精确性（不是泛泛而谈而是精准打击）、以及表达的简洁力度。"
    )
    return header + "\n\n" + "\n\n---\n\n".join(sections)