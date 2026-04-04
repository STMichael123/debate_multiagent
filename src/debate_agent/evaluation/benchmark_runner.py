from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any


def build_submission_template(gold_path: str | Path, submission_name: str = "submission_template_v1") -> dict[str, Any]:
    gold_payload = _load_json(gold_path)
    cases: list[dict[str, Any]] = []

    for gold_case in gold_payload.get("cases", []):
        task_type = gold_case["task_type"]
        cases.append(
            {
                "case_id": gold_case["case_id"],
                "task_type": task_type,
                "prediction": _empty_prediction_for_task(task_type),
            }
        )

    return {
        "submission_name": submission_name,
        "dataset_name": gold_payload.get("dataset_name"),
        "dataset_version": gold_payload.get("dataset_version"),
        "cases": cases,
    }


def score_benchmark_submission(gold_path: str | Path, submission_path: str | Path) -> dict[str, Any]:
    gold_payload = _load_json(gold_path)
    submission_payload = _load_json(submission_path)

    gold_cases = {case["case_id"]: case for case in gold_payload.get("cases", [])}
    submission_cases = {case["case_id"]: case for case in submission_payload.get("cases", [])}

    case_reports: list[dict[str, Any]] = []
    task_scores: dict[str, list[float]] = {}
    missing_case_ids: list[str] = []

    for case_id, gold_case in gold_cases.items():
        task_type = gold_case["task_type"]
        submission_case = submission_cases.get(case_id)
        if submission_case is None:
            missing_case_ids.append(case_id)
            case_reports.append(
                {
                    "case_id": case_id,
                    "task_type": task_type,
                    "score": 0.0,
                    "status": "missing_submission",
                }
            )
            task_scores.setdefault(task_type, []).append(0.0)
            continue

        score, details = _score_case(gold_case=gold_case, submission_case=submission_case)
        case_reports.append(
            {
                "case_id": case_id,
                "task_type": task_type,
                "score": score,
                "status": "scored",
                "details": details,
            }
        )
        task_scores.setdefault(task_type, []).append(score)

    extra_case_ids = sorted(case_id for case_id in submission_cases if case_id not in gold_cases)

    per_task = {
        task_type: {
            "case_count": len(scores),
            "average_score": _safe_div(sum(scores), len(scores)),
        }
        for task_type, scores in sorted(task_scores.items())
    }
    all_scores = [report["score"] for report in case_reports]
    task_breakdown = Counter(case["task_type"] for case in gold_payload.get("cases", []))

    return {
        "gold_dataset_name": gold_payload.get("dataset_name"),
        "submission_name": submission_payload.get("submission_name", "unnamed_submission"),
        "summary": {
            "gold_case_count": len(gold_cases),
            "submitted_case_count": len(submission_cases),
            "matched_case_count": len(gold_cases) - len(missing_case_ids),
            "overall_score": _safe_div(sum(all_scores), len(all_scores)),
            "task_breakdown": dict(task_breakdown),
        },
        "per_task": per_task,
        "missing_case_ids": missing_case_ids,
        "extra_case_ids": extra_case_ids,
        "case_reports": case_reports,
    }


def _score_case(gold_case: dict[str, Any], submission_case: dict[str, Any]) -> tuple[float, dict[str, Any]]:
    task_type = gold_case["task_type"]
    prediction = submission_case.get("prediction")
    if not isinstance(prediction, dict):
        return 0.0, {"reason": "prediction_missing_or_invalid"}

    if task_type == "argument_extraction":
        gold_values = {_normalize_text(argument["claim"]) for argument in gold_case["gold"].get("arguments", [])}
        predicted_values = {
            _normalize_text(argument.get("claim", ""))
            for argument in prediction.get("arguments", [])
            if _normalize_text(argument.get("claim", ""))
        }
        return _score_set_overlap(gold_values, predicted_values)

    if task_type == "evidence_extraction":
        gold_values = {
            _normalize_text(f"{item.get('title_or_desc', '')}|{item.get('source_ref', '')}")
            for item in gold_case["gold"].get("evidence_mentions", [])
        }
        predicted_values = {
            _normalize_text(f"{item.get('title_or_desc', '')}|{item.get('source_ref', '')}")
            for item in prediction.get("evidence_mentions", [])
            if item.get("title_or_desc") or item.get("source_ref")
        }
        return _score_set_overlap(gold_values, predicted_values)

    if task_type == "clash_identification":
        gold_values = {_normalize_text(item["topic_label"]) for item in gold_case["gold"].get("clash_points", [])}
        predicted_values = {
            _normalize_text(item.get("topic_label", ""))
            for item in prediction.get("clash_points", [])
            if _normalize_text(item.get("topic_label", ""))
        }
        return _score_set_overlap(gold_values, predicted_values)

    if task_type == "claim_role_classification":
        gold_value = str(gold_case["gold"].get("claim_role", "")).strip().lower()
        predicted_value = str(prediction.get("claim_role", "")).strip().lower()
        score = 1.0 if gold_value and gold_value == predicted_value else 0.0
        return score, {"gold": gold_value, "predicted": predicted_value}

    if task_type == "attack_type_classification":
        gold_value = str(gold_case["gold"].get("attack_type", "")).strip().lower()
        predicted_value = str(prediction.get("attack_type", "")).strip().lower()
        score = 1.0 if gold_value and gold_value == predicted_value else 0.0
        return score, {"gold": gold_value, "predicted": predicted_value}

    if task_type == "rebuttal_targeting":
        gold_values = {_normalize_text(value) for value in gold_case["gold"].get("response_to_argument_ids", [])}
        predicted_values = {
            _normalize_text(value)
            for value in prediction.get("response_to_argument_ids", [])
            if _normalize_text(value)
        }
        return _score_set_overlap(gold_values, predicted_values)

    return 0.0, {"reason": f"unsupported_task_type:{task_type}"}


def _empty_prediction_for_task(task_type: str) -> dict[str, Any]:
    if task_type == "argument_extraction":
        return {"arguments": []}
    if task_type == "evidence_extraction":
        return {"evidence_mentions": []}
    if task_type == "clash_identification":
        return {"clash_points": []}
    if task_type == "claim_role_classification":
        return {"claim_role": ""}
    if task_type == "attack_type_classification":
        return {"attack_type": ""}
    if task_type == "rebuttal_targeting":
        return {"response_to_argument_ids": []}
    return {}


def _score_set_overlap(gold_values: set[str], predicted_values: set[str]) -> tuple[float, dict[str, Any]]:
    if not gold_values and not predicted_values:
        return 1.0, {"precision": 1.0, "recall": 1.0, "f1": 1.0, "matched_count": 0}

    matched = gold_values.intersection(predicted_values)
    precision = _safe_div(len(matched), len(predicted_values))
    recall = _safe_div(len(matched), len(gold_values))
    f1 = _safe_div(2 * precision * recall, precision + recall) if precision or recall else 0.0
    return f1, {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "matched_count": len(matched),
        "gold_count": len(gold_values),
        "predicted_count": len(predicted_values),
        "missed": sorted(gold_values.difference(predicted_values)),
        "extra": sorted(predicted_values.difference(gold_values)),
    }


def _load_json(path: str | Path) -> dict[str, Any]:
    file_path = Path(path)
    return json.loads(file_path.read_text(encoding="utf-8"))


def _normalize_text(value: str) -> str:
    return " ".join(value.strip().lower().split())


def _safe_div(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return 0.0
    return numerator / denominator