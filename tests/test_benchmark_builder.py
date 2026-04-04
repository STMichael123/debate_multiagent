from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from debate_agent.evaluation import build_benchmark_dataset, load_structured_match


class BenchmarkBuilderTests(unittest.TestCase):
    def test_load_structured_match_requires_minimum_keys(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = Path(temp_dir) / "broken.json"
            file_path.write_text(json.dumps({"topic": "x"}, ensure_ascii=False), encoding="utf-8")

            with self.assertRaises(ValueError):
                load_structured_match(file_path)

    def test_build_benchmark_dataset_creates_seed_cases(self) -> None:
        sample_match = {
            "topic": "测试辩题",
            "match_info": {"round_name": "测试轮次"},
            "sides": {"affirmative": "正方", "negative": "反方"},
            "turns": [
                {
                    "turn_id": "T1",
                    "speaker_id": "S1",
                    "speaker_label": "正方一辩",
                    "side": "affirmative",
                    "phase": "constructive",
                    "raw_excerpt": "原句",
                    "normalized_text": "结构化表达",
                    "uncertainty_notes": [],
                },
                {
                    "turn_id": "T2",
                    "speaker_id": "S2",
                    "speaker_label": "反方一辩",
                    "side": "negative",
                    "phase": "closing",
                    "raw_excerpt": "结辩原句",
                    "normalized_text": "结辩结构化表达",
                    "uncertainty_notes": [],
                },
            ],
            "arguments": [
                {
                    "argument_id": "A1",
                    "turn_id": "T1",
                    "speaker_id": "S1",
                    "claim": "主张一",
                    "warrant": "理由一",
                    "impact": "影响一",
                    "tags": ["定义"],
                    "confidence": "high",
                }
            ],
            "evidence_mentions": [
                {
                    "evidence_id": "E1",
                    "turn_id": "T1",
                    "speaker_id": "S1",
                    "source_ref": "测试来源",
                    "title_or_desc": "测试证据",
                    "quoted_data": "测试数据",
                    "use_purpose": "测试用途",
                    "confidence": "high",
                }
            ],
            "clash_points": [
                {
                    "clash_point_id": "C1",
                    "topic_label": "争点一",
                    "summary": "双方在定义上冲突",
                    "related_argument_ids": ["A1"],
                    "open_questions": [],
                }
            ],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = Path(temp_dir) / "sample_match.json"
            file_path.write_text(json.dumps(sample_match, ensure_ascii=False), encoding="utf-8")

            dataset = build_benchmark_dataset([file_path], dataset_name="unit_test_seed")

        self.assertEqual(dataset["dataset_name"], "unit_test_seed")
        self.assertEqual(dataset["summary"]["match_count"], 1)
        self.assertEqual(dataset["summary"]["task_breakdown"]["argument_extraction"], 1)
        self.assertEqual(dataset["summary"]["task_breakdown"]["evidence_extraction"], 1)
        self.assertEqual(dataset["summary"]["task_breakdown"]["clash_identification"], 1)
        self.assertEqual(len(dataset["cases"]), 3)

        clash_case = next(case for case in dataset["cases"] if case["task_type"] == "clash_identification")
        self.assertEqual(clash_case["difficulty"], "hard")
        self.assertEqual(clash_case["gold"]["clash_points"][0]["related_argument_ids"], ["A1"])