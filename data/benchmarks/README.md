# Benchmarks

这里存放最小 benchmark seed 数据与后续生成产物。

当前策略：

1. 先从少量高精度比赛结构化 JSON 构建 seed。
2. 当前只覆盖可稳定金标化的三类任务：
   - `argument_extraction`
   - `evidence_extraction`
   - `clash_identification`
3. 暂不构建 `rebuttal_targeting`、`unanswered_point_tracking` 一类任务，因为现有 v2 结构尚未包含 `response_to_argument_id` 这类显式对齐字段。

v3 扩展：

1. 通过 [benchmark_v3_annotations.json](data/benchmarks/benchmark_v3_annotations.json) 为高精度样本补充 argument 级金标。
2. 当前新增三类攻防任务：
   - `claim_role_classification`
   - `attack_type_classification`
   - `rebuttal_targeting`
3. v3 的 `response_to_argument_ids`、`attack_type`、`claim_role` 目前是基于高精度 v2 摘要人工补标的第一版，适合作为 hardness 对比基线，不应误认为最终不可争议的唯一解释。

submission 最小格式：

1. 顶层包含 `submission_name`、`dataset_name`、`cases`。
2. 每个 case 通过 `case_id` 对齐 gold dataset。
3. `prediction` 字段按任务类型填写：
   - `argument_extraction` -> `prediction.arguments[].claim`
   - `evidence_extraction` -> `prediction.evidence_mentions[].title_or_desc` 与 `source_ref`
   - `clash_identification` -> `prediction.clash_points[].topic_label`
   - `claim_role_classification` -> `prediction.claim_role`
   - `attack_type_classification` -> `prediction.attack_type`
   - `rebuttal_targeting` -> `prediction.response_to_argument_ids[]`

评分规则：

1. `argument_extraction` 目前按 claim 文本做标准化后精确匹配。
2. `evidence_extraction` 目前按 `title_or_desc|source_ref` 的标准化字符串精确匹配。
3. `clash_identification` 目前按 `topic_label` 精确匹配。
4. `claim_role_classification` 与 `attack_type_classification` 目前按标签精确匹配。
5. `rebuttal_targeting` 按 `response_to_argument_ids` 集合做 precision / recall / f1。
6. 每个 case 输出 `precision`、`recall`、`f1` 或标签对比结果，总分取 case 平均值。

构建命令示例：

```bash
PYTHONPATH=src python scripts/build_benchmark_dataset.py <match-a.json> <match-b.json> --output data/benchmarks/seed_v1.json
```

构建 v3 seed 示例：

```bash
PYTHONPATH=src python scripts/build_benchmark_dataset.py <match-a.json> <match-b.json> --annotation-overlay data/benchmarks/benchmark_v3_annotations.json --dataset-name benchmark_seed_v3 --output data/benchmarks/seed_v3.json
```

seed 数据用途：

1. 固定少量高质量样本，避免调 hardness 时只靠主观感觉。
2. 先验证 schema、case 切分和任务边界，再决定是否扩展为更完整的 benchmark pipeline。
3. 未来补足 response link 字段后，再增量扩展到回应目标识别、未回应点追踪等任务。

运行命令示例：

```bash
PYTHONPATH=src python scripts/score_benchmark_submission.py data/benchmarks/seed_v1.json data/benchmarks/my_submission.json --output data/benchmarks/latest_report.json
```

初始化 submission 模板：

```bash
PYTHONPATH=src python scripts/init_benchmark_submission.py data/benchmarks/seed_v1.json --output data/benchmarks/submission_template.json
```

说明：

1. 当前 scorer 是最小版本，适合比较 prompt、agent 流程和 hardness 调整后的相对变化。
2. 当前并不处理同义改写、近义 claim 聚类或软匹配，因此更适合在相同输出协议下做版本对比，而不是做开放式 leaderboard。