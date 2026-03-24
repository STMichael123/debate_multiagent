# Evaluation

## 首版核心指标

1. 有效反驳率
2. 追问穿透力
3. 未回应点覆盖率
4. 证据引用率
5. 教练诊断一致性

## 每回合建议日志字段

1. `trace_id`
2. `session_id`
3. `turn_id`
4. `phase`
5. `profile_id`
6. `prompt_version`
7. `model_name`
8. `token_usage`
9. `latency_ms`
10. `rebuttal_target_ids`
11. `evidence_ids`
12. `pressure_score`
13. `coach_scores`
14. `hallucination_flag`

## 调试视图

1. Turn Timeline
2. Argument Graph
3. Clash Board
4. Prompt Trace

## 人工验证建议

1. 用三种辩题类型跑相同主链路。
2. 检查系统是否能持续追踪待回应点。
3. 检查对手每轮是否都明确攻击目标并提出追问。
4. 检查教练是否能稳定区分结构失误与表达失误。