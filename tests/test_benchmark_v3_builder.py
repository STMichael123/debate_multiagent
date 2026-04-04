from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from debate_agent.evaluation import build_benchmark_dataset


class BenchmarkV3BuilderTests(unittest.TestCase):
    def test_builder_emits_v3_argument_tasks_when_overlay_exists(self) -> None:
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
                    "phase": "rebuttal",
                    "raw_excerpt": "反驳原句",
                    "normalized_text": "反驳结构化表达",
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
                },
                {
                    "argument_id": "A2",
                    "turn_id": "T2",
                    "speaker_id": "S2",
                    "claim": "反驳一",
                    "warrant": "理由二",
                    "impact": "影响二",
                    "tags": ["反驳"],
                    "confidence": "high",
                }
            ],
            "evidence_mentions": [],
            "clash_points": [],
        }
        overlay = {
            "version": "0.3.0",
            "matches": {
                "sample_match": {
                    "arguments": {
                        "A1": {"claim_role": "setup", "attack_type": "none", "response_to_argument_ids": []},
                        "A2": {"claim_role": "rebuttal", "attack_type": "logical_challenge", "response_to_argument_ids": ["A1"]},
                    }
                }
            }
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            match_path = Path(temp_dir) / "sample_match.json"
            overlay_path = Path(temp_dir) / "overlay.json"
            match_path.write_text(json.dumps(sample_match, ensure_ascii=False), encoding="utf-8")
            overlay_path.write_text(json.dumps(overlay, ensure_ascii=False), encoding="utf-8")

            dataset = build_benchmark_dataset(
                [match_path],
                dataset_name="v3_test_seed",
                annotation_overlay_path=overlay_path,
            )

        task_breakdown = dataset["summary"]["task_breakdown"]
        self.assertEqual(task_breakdown["claim_role_classification"], 2)
        self.assertEqual(task_breakdown["attack_type_classification"], 1)
        self.assertEqual(task_breakdown["rebuttal_targeting"], 1)

        targeting_case = next(case for case in dataset["cases"] if case["task_type"] == "rebuttal_targeting")
        self.assertEqual(targeting_case["gold"]["response_to_argument_ids"], ["A1"])
        self.assertEqual(targeting_case["input"]["candidate_targets"][0]["argument_id"], "A1")