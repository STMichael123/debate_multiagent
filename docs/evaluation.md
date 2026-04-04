# Evaluation

## 评估目标

当前项目的评估对象已经从“单轮对手质量”扩展到完整训练工作流，因此评估也应分层：

1. 工程健康：项目是否可安装、可启动、可测试、可回归。
2. 接口健康：Web API、SSE、CLI 和存储能力是否稳定。
3. 内容质量：opening、turn、coach、closing、preparation 的输出是否有训练价值。
4. benchmark 回归：结构化抽取与攻防对齐任务是否退化。

## 当前自动化基线

仓库当前已有的自动化门禁包括：

1. pytest：覆盖应用服务、Web API、JSON/SQLite store、benchmark、evidence 和 opening 流程。
2. ruff：基础静态检查。
3. mypy：当前作为辅助检查，不阻塞 CI。
4. 覆盖率门槛：当前最低门槛为 30%，用于防止显著回退。

这意味着当前评估体系已经具备“回归防线”，但还没有到“高置信度质量量化”的程度。

## 核心指标分层

### 1. 工程与接口指标

1. 安装成功率：`pip install -e ".[dev]"` 是否稳定成功。
2. 启动成功率：CLI、uvicorn、Docker 启动是否稳定。
3. API 成功率：sessions、turn、opening、preparation、coach、closing 请求是否稳定返回 2xx。
4. SSE 完成率：opening brief 流式接口能否正常输出 `completed` 事件。
5. 存储成功率：JSON / SQLite save-load-delete 是否正常。
6. fallback 可用率：缺失 LLM 配置时，关键链路是否仍可返回 mock/fallback 结果。

### 2. 比赛内容指标

1. 有效反驳率：对手是否击中当前最关键的 target argument。
2. 追问穿透力：follow-up question 是否明确指向证明责任。
3. 未回应点覆盖率：pending response arguments 是否被持续追踪。
4. 证据使用质量：引用是否可追溯，是否与 claim 真正相关。
5. clash 推进度：输出是否让争点更集中，而不是扩散为泛泛讨论。

### 3. 立论内容指标

1. judge standard 清晰度：判断标准是否独立、明确、可判。
2. framework 完整度：argument cards 是否支撑 judge standard，而不是互相重复。
3. opening 成稿度：spoken text 是否可直接朗读，而不是半成品提纲。
4. 时长匹配度：内容密度是否符合 target duration minutes。
5. opening coach 可执行性：反馈是否能直接转化为改稿动作。

### 4. 评判内容指标

1. 教练诊断一致性：是否稳定区分逻辑失守、回应失守和表达问题。
2. 对手识别准确度：教练是否正确识别对手主攻路径。
3. 建议动作性：是否给出明确下一轮优先级，而不是泛泛鼓励。
4. timer plan 合理性：时间规划是否与 phase 和 speaker side 一致。

### 5. 备赛内容指标

1. evidence 多样性：是否同时覆盖数据、研究和情景层面。
2. theory point 可迁移性：学理总结是否能复用到 opening 和 turn。
3. argument seed 可打性：seed 是否可直接转化成可辩论的论点。
4. 上游复用率：preparation packet 是否实质进入 opening/turn prompt，而不是只被存档。

## 推荐日志字段

建议按链路记录日志字段，而不是只记录单轮辩论：

1. `trace_id`
2. `session_id`
3. `phase`
4. `operation_type`
5. `profile_id`
6. `prompt_template`
7. `model_name`
8. `token_usage`
9. `latency_ms`
10. `web_search_enabled`
11. `retrieved_evidence_ids`
12. `preparation_packet_count`
13. `selected_agent`
14. `pressure_score`
15. `coach_scores`
16. `stream_event_count`
17. `fallback_used`
18. `hallucination_flag`

## 调试视图

当前最值得保留和扩展的调试视图：

1. Turn Timeline：观察 round-by-round 状态推进。
2. Clash Board：观察争点是否收敛。
3. Prompt Trace：观察模板输入和输出协议。
4. Opening Workspace Snapshot：观察 framework 与 brief 的打磨过程。
5. Evidence Panel：观察 dossier、web search 与 preparation evidence 的合流结果。

## 人工评审建议

### Turn 评审

1. 对手是否锁定了真正值得攻击的目标，而不是抓枝节。
2. 追问是否带证明责任，而不是只求语气强势。
3. 证据是否自然服务论证，而不是表面堆料。

### Opening 评审

1. judge standard 是否可以真正裁判本题。
2. argument cards 是否是从标准延伸出的赢点，而不是简单复述立场。
3. 一辩稿是否能直接朗读，是否存在段落断裂和跳步。

### Coach 评审

1. 教练是否识别了对手真正击中的漏洞。
2. 教练是否把结构问题和表达问题分开。
3. 建议是否能直接转化为下一轮回答。

### Preparation 评审

1. 资料是否足够支持 opening 和 turn，不只是检索到相关网页。
2. theory points 是否抽象得当，既不空泛也不过度细碎。
3. argument seeds 是否可以被真实辩手直接拿来扩写。

## Benchmark 的位置

当前 benchmark 主要覆盖结构化抽取和攻防对齐任务，适合做以下事情：

1. 比较不同 prompt 版本的结构稳定性。
2. 比较 argument analysis 或 response targeting 是否退化。
3. 给 retrieval / analysis / orchestration 的底层变更提供最小回归集。

它目前不直接衡量以下内容：

1. opening brief 的整体说服力。
2. 教练建议的实战价值。
3. Web 端交互体验和流式展示质量。
4. 长陈词的朗读感和收束质量。

因此，benchmark 应被视为回归底线，而不是完整产品质量的唯一指标。