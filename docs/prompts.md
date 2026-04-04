# Prompt Design

## 当前 Prompt 体系

项目当前不再只有“对手 + 教练”两类 prompt，而是围绕完整训练闭环维护一组模板家族：

1. 对辩输出：opponent、closing、inquiry 相关 prompt。
2. 分析与评判：argument analysis、coach、opening coach。
3. 立论生成：opening framework、opening draft、opening draft stream。

所有模板都遵循同一条原则：尽量把自由生成约束成结构化输入和结构化输出，让前后处理与回归测试更稳定。

## 共享设计原则

1. 明确角色：每个 agent 都必须像专职辩手、教练或稿件架构师工作，而不是泛化聊天助手。
2. 明确任务：prompt 会把当前轮次的唯一目标写清楚，避免模型同时做太多事。
3. 明确上下文：session、profile、recent turns、clash、evidence 和 preparation packet 均以可追踪字段注入。
4. 明确输出：除少数纯文本场景外，大部分模板都要求只返回 JSON 对象，降低后处理歧义。
5. 明确自检：关键模板都带 self check，强制模型在输出前校验攻击对象、证据使用和目标是否匹配。
6. 反幻觉优先：多处模板显式要求“证据不足时改用机制攻击或逻辑归纳，而不是编造事实”。

## 模板家族

### 1. Opponent Template

定位：高压对手，在当前 clash 上推进比赛。

推荐分层：

1. `system_role`
2. `debate_mission`
3. `debate_profile`
4. `phase_instruction`
5. `live_context`
6. `evidence_packet`
7. `response_contract`
8. `self_check`
9. `reference_examples`

当前特点：

1. 显式输入 opening brief packet，使对手可针对我方一辩骨架提前设伏。
2. 显式输入 preparation packet，使比赛链路可以继承赛前研究成果。
3. 要求输出 rebuttal target、attack strategy、spoken text、follow-up questions 和 evidence citations。

### 2. Coach Template

定位：结构化回合教练，不参与继续对辩。

推荐分层：

1. `system_role`
2. `coaching_mission`
3. `evaluation_rubric`
4. `live_context`
5. `opponent_move_review`
6. `diagnosis_contract`
7. `improvement_contract`
8. `self_check`
9. `reference_examples`

当前特点：

1. 不默认对手正确，先判断对手攻击是否成立。
2. 必须区分逻辑问题、结构问题、回应问题、证据问题和表达问题。
3. 输出中必须带下一轮可执行动作。

### 3. Closing Template

定位：长陈词生成。

当前特点：

1. 明确要求围绕 judge standard、2 到 3 个赢点和对方未完成证明责任收束。
2. Evidence packet 中额外注入 evidence quality summary 和 evidence usage guidance。
3. 对低可信网页转述、论坛摘要和资料拼贴明确降级，不允许包装成权威研究。

### 4. Argument Analysis Template

定位：把用户本轮输入拆成结构化状态更新材料。

当前特点：

1. 输出 arguments、clash points、pending response arguments 和 round summary。
2. 是 MatchEngine 更新 session state 的前置分析器。
3. 为后续 opponent prompt 提供更稳定的目标论点和 clash 摘要。

### 5. Opening Framework Template

定位：一辩框架稿架构师。

当前特点：

1. 强制区分 judge standard 和 argument cards，禁止把判断标准直接写成论点。
2. 输出的是可编辑框架稿，而不是最终可朗读成稿。
3. 目标是生成后续可扩写、可继续打磨的结构骨架。

### 6. Opening Draft Template

定位：基于框架稿生成完整一辩成稿。

当前特点：

1. 输入 opening framework 和 target duration minutes。
2. 输出 strategy summary、outline、spoken text 与 framework 回填结果。
3. 目标是写成可直接朗读的正式 opening brief，而不是提纲。

### 7. Opening Draft Stream Template

定位：服务 Web 端流式一辩稿生成。

当前特点：

1. 适配 SSE 增量输出场景。
2. 前端会消费 `opening_chunk`、`completed`、`error` 等事件。
3. 模板职责与 Opening Draft 接近，但更强调稳定分段和逐步展开。

### 8. Opening Coach Template

定位：专门点评 opening brief，而不是点评整轮对辩。

当前特点：

1. 关注 judge standard、框架完整度、论点衔接、证据可上场性和朗读性。
2. 输出 scope 为 `opening_brief` 的稿件反馈。
3. 与回合教练共享“结构诊断 + 可执行建议”原则，但评价对象不同。

## 模板输入来源

Session 变量：

1. `topic`
2. `user_side`
3. `agent_side`
4. `current_phase`
5. `opening_brief_packet`
6. `preparation_packet`

Profile 变量：

1. `debate_type`
2. `judge_standard`
3. `burden_rules`
4. `preferred_attack_patterns`
5. `preferred_question_patterns`
6. `evidence_policy`
7. `style_constraints`

State 变量：

1. `active_clash_points`
2. `pending_response_arguments`
3. `recent_turns_summary`
4. `latest_user_turn`
5. `latest_opponent_turn`

Retrieval 变量：

1. `evidence_packet`
2. `evidence_quality_summary`
3. `evidence_usage_guidance`
4. `reference_examples`

## 输出契约策略

当前 prompt 体系尽量把输出收束为结构化字段，主要原因有三点：

1. 便于后端把结果落入 domain model，而不是依赖脆弱的自然语言解析。
2. 便于测试对关键字段做断言，例如 `master_plan`、`pressure_score`、`score_card`、`outline`。
3. 便于 benchmark 和人工评审把“内容质量”与“协议稳定性”分开观察。

典型输出字段包括：

1. 对手输出：`rebuttal_target_ids`、`attack_strategy`、`spoken_text`、`follow_up_questions`
2. 教练输出：`round_verdict`、`user_missed_responses`、`score_card`、`next_round_priorities`
3. 陈词输出：`strategy_summary`、`outline`、`spoken_text`、`evidence_citations`
4. 框架输出：`judge_standard`、`framework_summary`、`argument_cards`

## 参考示例与检索材料

当前 prompt 体系支持两类外部补料：

1. ExampleBank：提供结构参考和风格参考，但明确禁止复制具体论点和证据。
2. Evidence packet：提供可追溯资料；如果证据不足，应切换为逻辑机制推导，而不是编造。

这种设计的核心不是让模型“说得更像人”，而是让模型在固定业务目标下输出更可控、更可回归的内容。