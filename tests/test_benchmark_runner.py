from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from debate_agent.evaluation import build_submission_template, score_benchmark_submission


class BenchmarkRunnerTests(unittest.TestCase):
    def test_build_submission_template_preserves_case_ids(self) -> None:
        gold_dataset = {
            "dataset_name": "seed",
            "dataset_version": "0.1.0",
            "cases": [
                {"case_id": "case-1", "task_type": "argument_extraction", "gold": {"arguments": []}},
                {"case_id": "case-2", "task_type": "evidence_extraction", "gold": {"evidence_mentions": []}},
            ],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            gold_path = Path(temp_dir) / "gold.json"
            gold_path.write_text(json.dumps(gold_dataset, ensure_ascii=False), encoding="utf-8")

            template = build_submission_template(gold_path, submission_name="template")

        self.assertEqual(template["submission_name"], "template")
        self.assertEqual(template["dataset_name"], "seed")
        self.assertEqual(template["cases"][0]["case_id"], "case-1")
        self.assertEqual(template["cases"][0]["prediction"], {"arguments": []})

    def test_perfect_submission_scores_full_marks(self) -> None:
        gold_dataset = {
            "dataset_name": "seed",
            "cases": [
                {
                    "case_id": "case-1",
                    "task_type": "argument_extraction",
                    "gold": {
                        "arguments": [
                            {"claim": "主张一"},
                            {"claim": "主张二"},
                        ]
                    },
                },
                {
                    "case_id": "case-2",
                    "task_type": "evidence_extraction",
                    "gold": {
                        "evidence_mentions": [
                            {"title_or_desc": "证据一", "source_ref": "来源一"}
                        ]
                    },
                },
                {
                    "case_id": "case-3",
                    "task_type": "clash_identification",
                    "gold": {
                        "clash_points": [
                            {"topic_label": "争点一"}
                        ]
                    },
                },
            ],
        }
        submission = {
            "submission_name": "perfect",
            "cases": [
                {
                    "case_id": "case-1",
                    "prediction": {
                        "arguments": [{"claim": "主张一"}, {"claim": "主张二"}]
                    },
                },
                {
                    "case_id": "case-2",
                    "prediction": {
                        "evidence_mentions": [{"title_or_desc": "证据一", "source_ref": "来源一"}]
                    },
                },
                {
                    "case_id": "case-3",
                    "prediction": {
                        "clash_points": [{"topic_label": "争点一"}]
                    },
                },
            ],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            gold_path = Path(temp_dir) / "gold.json"
            submission_path = Path(temp_dir) / "submission.json"
            gold_path.write_text(json.dumps(gold_dataset, ensure_ascii=False), encoding="utf-8")
            submission_path.write_text(json.dumps(submission, ensure_ascii=False), encoding="utf-8")

            report = score_benchmark_submission(gold_path, submission_path)

        self.assertEqual(report["summary"]["overall_score"], 1.0)
        self.assertEqual(report["per_task"]["argument_extraction"]["average_score"], 1.0)
        self.assertEqual(report["per_task"]["evidence_extraction"]["average_score"], 1.0)
        self.assertEqual(report["per_task"]["clash_identification"]["average_score"], 1.0)

    def test_missing_and_partial_submission_reduce_scores(self) -> None:
        gold_dataset = {
            "dataset_name": "seed",
            "cases": [
                {
                    "case_id": "case-1",
                    "task_type": "argument_extraction",
                    "gold": {
                        "arguments": [
                            {"claim": "主张一"},
                            {"claim": "主张二"},
                        ]
                    },
                },
                {
                    "case_id": "case-2",
                    "task_type": "clash_identification",
                    "gold": {
                        "clash_points": [
                            {"topic_label": "争点一"}
                        ]
                    },
                },
            ],
        }
        submission = {
            "submission_name": "partial",
            "cases": [
                {
                    "case_id": "case-1",
                    "prediction": {
                        "arguments": [{"claim": "主张一"}]
                    },
                }
            ],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            gold_path = Path(temp_dir) / "gold.json"
            submission_path = Path(temp_dir) / "submission.json"
            gold_path.write_text(json.dumps(gold_dataset, ensure_ascii=False), encoding="utf-8")
            submission_path.write_text(json.dumps(submission, ensure_ascii=False), encoding="utf-8")

            report = score_benchmark_submission(gold_path, submission_path)

        self.assertLess(report["summary"]["overall_score"], 1.0)
        self.assertEqual(report["summary"]["matched_case_count"], 1)
        self.assertEqual(report["missing_case_ids"], ["case-2"])
        self.assertAlmostEqual(report["per_task"]["argument_extraction"]["average_score"], 2 / 3)

    def test_v3_classification_and_targeting_tasks_can_be_scored(self) -> None:
        gold_dataset = {
            "dataset_name": "seed_v3",
            "cases": [
                {
                    "case_id": "case-role",
                    "task_type": "claim_role_classification",
                    "gold": {"claim_role": "rebuttal"},
                },
                {
                    "case_id": "case-attack",
                    "task_type": "attack_type_classification",
                    "gold": {"attack_type": "logical_challenge"},
                },
                {
                    "case_id": "case-target",
                    "task_type": "rebuttal_targeting",
                    "gold": {"response_to_argument_ids": ["A1", "A2"]},
                },
            ],
        }
        submission = {
            "submission_name": "v3_submission",
            "cases": [
                {"case_id": "case-role", "prediction": {"claim_role": "rebuttal"}},
                {"case_id": "case-attack", "prediction": {"attack_type": "logical_challenge"}},
                {"case_id": "case-target", "prediction": {"response_to_argument_ids": ["A1"]}},
            ],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            gold_path = Path(temp_dir) / "gold.json"
            submission_path = Path(temp_dir) / "submission.json"
            gold_path.write_text(json.dumps(gold_dataset, ensure_ascii=False), encoding="utf-8")
            submission_path.write_text(json.dumps(submission, ensure_ascii=False), encoding="utf-8")

            report = score_benchmark_submission(gold_path, submission_path)

        self.assertEqual(report["per_task"]["claim_role_classification"]["average_score"], 1.0)
        self.assertEqual(report["per_task"]["attack_type_classification"]["average_score"], 1.0)
        self.assertAlmostEqual(report["per_task"]["rebuttal_targeting"]["average_score"], 2 / 3)