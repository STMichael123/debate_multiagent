# Benchmarks

这里存放当前项目的最小 benchmark 数据、标注覆盖层和 submission 模板。

## Benchmark 在当前产品里的定位

当前产品已经扩展到 preparation、opening、turn、coach、closing 等多条链路，但 benchmark 仍然主要服务于“结构化分析与攻防对齐”的回归，而不是直接评价完整用户体验。

它当前最适合回答的问题是：

1. argument analysis 有没有退化。
2. evidence / clash 抽取协议有没有变差。
3. response targeting 等结构化攻防字段是否比上一版更稳定。

它暂时不直接评价：

1. opening brief 的说服力。
2. closing 的朗读质量。
3. coach 建议的训练价值。
4. Web 交互和 SSE 体验。

## 当前数据版本

基础策略：

1. 先从少量高精度比赛结构化 JSON 构建 seed。
2. 先做可以稳定金标化的任务，再逐步扩展。
3. 保持 submission 协议简单，优先服务回归而不是排行榜。

v1 任务：

1. `argument_extraction`
2. `evidence_extraction`
3. `clash_identification`

v3 扩展任务：

1. `claim_role_classification`
2. `attack_type_classification`
3. `rebuttal_targeting`

说明：

1. [benchmark_v3_annotations.json](data/benchmarks/benchmark_v3_annotations.json) 为高精度样本补充了 argument 级标注。
2. `response_to_argument_ids`、`attack_type`、`claim_role` 属于第一版人工补标，更适合作为 hardness 对比基线，而不是不可争议的唯一金标。

## Submission 格式

submission 最小格式：

1. 顶层包含 `submission_name`、`dataset_name`、`cases`。
2. 每个 case 通过 `case_id` 对齐 gold dataset。
3. `prediction` 按任务类型填写：
   - `argument_extraction` -> `prediction.arguments[].claim`
   - `evidence_extraction` -> `prediction.evidence_mentions[].title_or_desc` 与 `source_ref`
   - `clash_identification` -> `prediction.clash_points[].topic_label`
   - `claim_role_classification` -> `prediction.claim_role`
   - `attack_type_classification` -> `prediction.attack_type`
   - `rebuttal_targeting` -> `prediction.response_to_argument_ids[]`

当前模板文件：

1. `submission_template.json`
2. `submission_template_v3.json`
3. `sample_submission.json`

## 评分规则

1. `argument_extraction`：按 claim 文本标准化后精确匹配。
2. `evidence_extraction`：按 `title_or_desc|source_ref` 标准化字符串精确匹配。
3. `clash_identification`：按 `topic_label` 精确匹配。
4. `claim_role_classification`：按标签精确匹配。
5. `attack_type_classification`：按标签精确匹配。
6. `rebuttal_targeting`：按 `response_to_argument_ids` 集合计算 precision / recall / f1。

每个 case 输出局部结果，总分取 case 平均值。

## 构建与评分命令

构建 v1 seed：

```bash
PYTHONPATH=src python scripts/build_benchmark_dataset.py <match-a.json> <match-b.json> --output data/benchmarks/seed_v1.json
```

构建 v3 seed：

```bash
PYTHONPATH=src python scripts/build_benchmark_dataset.py <match-a.json> <match-b.json> --annotation-overlay data/benchmarks/benchmark_v3_annotations.json --dataset-name benchmark_seed_v3 --output data/benchmarks/seed_v3.json
```

初始化 submission 模板：

```bash
PYTHONPATH=src python scripts/init_benchmark_submission.py data/benchmarks/seed_v1.json --output data/benchmarks/submission_template.json
```

运行评分：

```bash
PYTHONPATH=src python scripts/score_benchmark_submission.py data/benchmarks/seed_v1.json data/benchmarks/my_submission.json --output data/benchmarks/latest_report.json
```

## 维护建议

1. benchmark 继续保持“小而准”，优先覆盖最容易被流程改动破坏的结构字段。
2. 新增任务前，先确认 gold 字段是否足够稳定，而不是为了追求覆盖率强行扩表。
3. 如果未来要覆盖 opening 或 coach，建议单独设计人工 rubric，而不是硬塞进现有 extraction scorer。
4. 当前 scorer 不做同义改写、claim 聚类或软匹配，因此更适合同协议版本对比，不适合开放式 leaderboard。