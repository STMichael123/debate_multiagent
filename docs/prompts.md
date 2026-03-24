# Prompt Design

## 对手 Agent

推荐分层：

1. `system_role`
2. `debate_mission`
3. `debate_profile`
4. `phase_instruction`
5. `live_context`
6. `evidence_packet`
7. `response_contract`
8. `self_check`

核心原则：

1. 不是聊天助手，而是高水平对手。
2. 不是全面讨论，而是精准反驳。
3. 每轮必须推进当前最重要的 clash。
4. 结尾必须抛出具体追问。
5. 不能编造事实。

## 教练 Agent

推荐分层：

1. `system_role`
2. `coaching_mission`
3. `evaluation_rubric`
4. `live_context`
5. `opponent_move_review`
6. `diagnosis_contract`
7. `improvement_contract`
8. `self_check`

核心原则：

1. 不参与继续对辩。
2. 必须指出具体失误。
3. 必须区分逻辑问题和表达问题。
4. 必须给出下一轮可执行动作。

## 模板输入来源

1. Session 变量：`topic`、`user_side`、`agent_side`、`current_phase`。
2. Profile 变量：`debate_type`、`judge_standard`、`burden_rules`。
3. State 变量：`active_clash_points`、`pending_response_arguments`、`recent_turns_summary`。
4. Retrieval 变量：`evidence_packet`。