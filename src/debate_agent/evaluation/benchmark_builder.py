from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence


SUPPORTED_CASE_PHASES = {
    "constructive",
    "opening",
    "rebuttal",
    "cross_examination",
    "crossfire",
    "free_speech",
    "free_debate",
    "moderator_qna",
    "summary",
    "closing",
}


def load_structured_match(path: str | Path) -> dict[str, Any]:
    file_path = Path(path)
    payload = json.loads(file_path.read_text(encoding="utf-8"))

    required_keys = {"topic", "match_info", "turns", "arguments", "evidence_mentions", "clash_points"}
    missing = required_keys.difference(payload)
    if missing:
        missing_keys = ", ".join(sorted(missing))
        raise ValueError(f"Structured match is missing required keys: {missing_keys}")

    return payload


def load_benchmark_annotation_overlay(path: str | Path) -> dict[str, Any]:
    file_path = Path(path)
    payload = json.loads(file_path.read_text(encoding="utf-8"))
    return payload.get("matches", {})


def build_benchmark_dataset(
    source_paths: Sequence[str | Path],
    dataset_name: str = "benchmark_seed_v1",
    annotation_overlay_path: str | Path | None = None,
) -> dict[str, Any]:
    if not source_paths:
        raise ValueError("At least one structured match source is required.")

    dataset_sources: list[dict[str, Any]] = []
    dataset_cases: list[dict[str, Any]] = []
    annotation_overlays = load_benchmark_annotation_overlay(annotation_overlay_path) if annotation_overlay_path else {}

    for source_index, source_path in enumerate(source_paths, start=1):
        file_path = Path(source_path)
        match_payload = load_structured_match(file_path)
        match_id = _build_match_id(match_payload=match_payload, file_path=file_path, source_index=source_index)
        source_label = file_path.stem
        match_overlay = annotation_overlays.get(source_label, {})

        dataset_sources.append(
            {
                "match_id": match_id,
                "source_label": source_label,
                "source_path": str(file_path),
                "topic": match_payload["topic"],
                "round_name": match_payload["match_info"].get("round_name", "unknown"),
                "turn_count": len(match_payload.get("turns", [])),
                "argument_count": len(match_payload.get("arguments", [])),
                "evidence_count": len(match_payload.get("evidence_mentions", [])),
                "clash_count": len(match_payload.get("clash_points", [])),
                "annotation_overlay": bool(match_overlay),
            }
        )
        dataset_cases.extend(
            _build_match_cases(
                match_id=match_id,
                source_label=source_label,
                match_payload=match_payload,
                match_overlay=match_overlay,
            )
        )

    task_breakdown = Counter(case["task_type"] for case in dataset_cases)
    difficulty_breakdown = Counter(case["difficulty"] for case in dataset_cases)
    has_v3_overlay = bool(annotation_overlays)
    dataset_version = "0.3.0" if has_v3_overlay else "0.1.0"
    notes = [
        "当前 seed 覆盖基于现有 v2 标注可稳定构建的任务：argument_extraction、evidence_extraction、clash_identification。",
    ]
    if has_v3_overlay:
        notes.extend(
            [
                "当前数据集已通过 v3 overlay 扩展出 argument 级金标：claim_role、attack_type、response_to_argument_ids。",
                "新增任务 claim_role_classification、attack_type_classification、rebuttal_targeting，可开始评测攻防 hardness。",
                "当前 response_to 与 attack_type 属于第一版人工补标，适合作为相对比较基线，不应视为唯一不可争议标答。",
            ]
        )
    else:
        notes.append("尚未构建 rebuttal_targeting 或 unanswered_point_tracking，因为源标注尚未提供 response_to_argument_id 一类的金标链接。")

    return {
        "dataset_name": dataset_name,
        "dataset_version": dataset_version,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "task_types": sorted(task_breakdown),
        "sources": dataset_sources,
        "cases": dataset_cases,
        "summary": {
            "match_count": len(dataset_sources),
            "case_count": len(dataset_cases),
            "task_breakdown": dict(task_breakdown),
            "difficulty_breakdown": dict(difficulty_breakdown),
        },
        "notes": notes,
    }


def _build_match_cases(
    match_id: str,
    source_label: str,
    match_payload: dict[str, Any],
    match_overlay: dict[str, Any],
) -> list[dict[str, Any]]:
    turns_by_id = {turn["turn_id"]: turn for turn in match_payload.get("turns", [])}
    turn_order = {turn["turn_id"]: index for index, turn in enumerate(match_payload.get("turns", []), start=1)}
    arguments_by_turn = _group_by_key(match_payload.get("arguments", []), "turn_id")
    evidence_by_turn = _group_by_key(match_payload.get("evidence_mentions", []), "turn_id")
    arguments_by_id = {argument["argument_id"]: argument for argument in match_payload.get("arguments", [])}
    argument_annotations = match_overlay.get("arguments", {})

    cases: list[dict[str, Any]] = []

    for turn in match_payload.get("turns", []):
        phase = str(turn.get("phase", "unknown"))
        if phase not in SUPPORTED_CASE_PHASES:
            continue

        turn_id = turn["turn_id"]
        turn_arguments = arguments_by_turn.get(turn_id, [])
        turn_evidence = evidence_by_turn.get(turn_id, [])

        if turn_arguments:
            cases.append(
                {
                    "case_id": f"{match_id}:argument_extraction:{turn_id}",
                    "task_type": "argument_extraction",
                    "difficulty": _infer_turn_difficulty(task_type="argument_extraction", phase=phase, item_count=len(turn_arguments)),
                    "source_match_id": match_id,
                    "source_label": source_label,
                    "source_turn_ids": [turn_id],
                    "input": _build_turn_input(match_payload=match_payload, turn=turn),
                    "gold": {
                        "arguments": [
                            {
                                "argument_id": argument["argument_id"],
                                "claim": argument["claim"],
                                "warrant": argument.get("warrant"),
                                "impact": argument.get("impact"),
                                "tags": argument.get("tags", []),
                                "confidence": argument.get("confidence", "unknown"),
                            }
                            for argument in turn_arguments
                        ]
                    },
                    "metadata": {
                        "round_name": match_payload["match_info"].get("round_name", "unknown"),
                        "speaker_id": turn.get("speaker_id"),
                        "speaker_label": turn.get("speaker_label"),
                        "side": turn.get("side"),
                        "phase": phase,
                    },
                }
            )

        if turn_evidence:
            cases.append(
                {
                    "case_id": f"{match_id}:evidence_extraction:{turn_id}",
                    "task_type": "evidence_extraction",
                    "difficulty": _infer_turn_difficulty(task_type="evidence_extraction", phase=phase, item_count=len(turn_evidence)),
                    "source_match_id": match_id,
                    "source_label": source_label,
                    "source_turn_ids": [turn_id],
                    "input": _build_turn_input(match_payload=match_payload, turn=turn),
                    "gold": {
                        "evidence_mentions": [
                            {
                                "evidence_id": evidence["evidence_id"],
                                "title_or_desc": evidence.get("title_or_desc"),
                                "source_ref": evidence.get("source_ref"),
                                "quoted_data": evidence.get("quoted_data"),
                                "use_purpose": evidence.get("use_purpose"),
                                "confidence": evidence.get("confidence", "unknown"),
                            }
                            for evidence in turn_evidence
                        ]
                    },
                    "metadata": {
                        "round_name": match_payload["match_info"].get("round_name", "unknown"),
                        "speaker_id": turn.get("speaker_id"),
                        "speaker_label": turn.get("speaker_label"),
                        "side": turn.get("side"),
                        "phase": phase,
                    },
                }
            )

    if match_payload.get("clash_points"):
        cases.append(_build_clash_case(match_id=match_id, source_label=source_label, match_payload=match_payload, turns_by_id=turns_by_id))

    for argument in match_payload.get("arguments", []):
        annotation = argument_annotations.get(argument["argument_id"])
        if not annotation:
            continue
        turn = turns_by_id.get(argument["turn_id"])
        if turn is None:
            continue

        claim_role = annotation.get("claim_role")
        if claim_role:
            cases.append(
                {
                    "case_id": f"{match_id}:claim_role_classification:{argument['argument_id']}",
                    "task_type": "claim_role_classification",
                    "difficulty": "medium",
                    "source_match_id": match_id,
                    "source_label": source_label,
                    "source_turn_ids": [argument["turn_id"]],
                    "input": _build_argument_input(match_payload=match_payload, turn=turn, argument=argument),
                    "gold": {"claim_role": claim_role},
                    "metadata": {
                        "argument_id": argument["argument_id"],
                        "phase": turn.get("phase"),
                        "side": turn.get("side"),
                    },
                }
            )

        attack_type = annotation.get("attack_type")
        if attack_type and attack_type != "none":
            cases.append(
                {
                    "case_id": f"{match_id}:attack_type_classification:{argument['argument_id']}",
                    "task_type": "attack_type_classification",
                    "difficulty": "hard",
                    "source_match_id": match_id,
                    "source_label": source_label,
                    "source_turn_ids": [argument["turn_id"]],
                    "input": _build_argument_input(match_payload=match_payload, turn=turn, argument=argument),
                    "gold": {"attack_type": attack_type},
                    "metadata": {
                        "argument_id": argument["argument_id"],
                        "phase": turn.get("phase"),
                        "side": turn.get("side"),
                    },
                }
            )

        response_to_argument_ids = annotation.get("response_to_argument_ids", [])
        if response_to_argument_ids:
            candidate_targets = _build_candidate_targets(
                current_argument=argument,
                arguments_by_id=arguments_by_id,
                turn_order=turn_order,
                turns_by_id=turns_by_id,
            )
            cases.append(
                {
                    "case_id": f"{match_id}:rebuttal_targeting:{argument['argument_id']}",
                    "task_type": "rebuttal_targeting",
                    "difficulty": "hard",
                    "source_match_id": match_id,
                    "source_label": source_label,
                    "source_turn_ids": [argument["turn_id"]],
                    "input": {
                        **_build_argument_input(match_payload=match_payload, turn=turn, argument=argument),
                        "candidate_targets": candidate_targets,
                    },
                    "gold": {"response_to_argument_ids": response_to_argument_ids},
                    "metadata": {
                        "argument_id": argument["argument_id"],
                        "phase": turn.get("phase"),
                        "side": turn.get("side"),
                    },
                }
            )

    return cases


def _build_clash_case(match_id: str, source_label: str, match_payload: dict[str, Any], turns_by_id: dict[str, dict[str, Any]]) -> dict[str, Any]:
    argument_index = {argument["argument_id"]: argument for argument in match_payload.get("arguments", [])}
    related_turn_ids = sorted(
        {
            argument["turn_id"]
            for clash in match_payload.get("clash_points", [])
            for argument_id in clash.get("related_argument_ids", [])
            for argument in [argument_index.get(argument_id)]
            if argument is not None and argument.get("turn_id") in turns_by_id
        }
    )

    input_arguments = [
        {
            "argument_id": argument["argument_id"],
            "turn_id": argument["turn_id"],
            "speaker_id": argument.get("speaker_id"),
            "claim": argument.get("claim"),
            "tags": argument.get("tags", []),
        }
        for argument in match_payload.get("arguments", [])
    ]

    return {
        "case_id": f"{match_id}:clash_identification:match",
        "task_type": "clash_identification",
        "difficulty": "hard",
        "source_match_id": match_id,
        "source_label": source_label,
        "source_turn_ids": related_turn_ids,
        "input": {
            "topic": match_payload["topic"],
            "sides": match_payload.get("sides", {}),
            "arguments": input_arguments,
        },
        "gold": {
            "clash_points": [
                {
                    "clash_point_id": clash["clash_point_id"],
                    "topic_label": clash.get("topic_label"),
                    "summary": clash.get("summary"),
                    "related_argument_ids": clash.get("related_argument_ids", []),
                }
                for clash in match_payload.get("clash_points", [])
            ]
        },
        "metadata": {
            "round_name": match_payload["match_info"].get("round_name", "unknown"),
            "argument_count": len(match_payload.get("arguments", [])),
            "clash_count": len(match_payload.get("clash_points", [])),
        },
    }


def _build_turn_input(match_payload: dict[str, Any], turn: dict[str, Any]) -> dict[str, Any]:
    return {
        "topic": match_payload["topic"],
        "side": turn.get("side"),
        "phase": turn.get("phase"),
        "speaker_label": turn.get("speaker_label"),
        "raw_excerpt": turn.get("raw_excerpt"),
        "normalized_text": turn.get("normalized_text"),
    }


def _build_argument_input(match_payload: dict[str, Any], turn: dict[str, Any], argument: dict[str, Any]) -> dict[str, Any]:
    return {
        "topic": match_payload["topic"],
        "side": turn.get("side"),
        "phase": turn.get("phase"),
        "speaker_label": turn.get("speaker_label"),
        "turn_normalized_text": turn.get("normalized_text"),
        "argument": {
            "argument_id": argument["argument_id"],
            "claim": argument.get("claim"),
            "warrant": argument.get("warrant"),
            "impact": argument.get("impact"),
            "tags": argument.get("tags", []),
        },
    }


def _build_match_id(match_payload: dict[str, Any], file_path: Path, source_index: int) -> str:
    round_name = str(match_payload.get("match_info", {}).get("round_name", "match"))
    topic = str(match_payload.get("topic", file_path.stem))
    slug = _slugify(f"{file_path.stem}-{round_name}-{topic}")
    if slug:
        return slug
    return f"match-{source_index:03d}"


def _slugify(text: str) -> str:
    lowered = text.strip().lower()
    chars: list[str] = []
    last_dash = False
    for char in lowered:
        if char.isalnum():
            chars.append(char)
            last_dash = False
            continue
        if not last_dash:
            chars.append("-")
            last_dash = True
    return "".join(chars).strip("-")


def _group_by_key(items: Iterable[dict[str, Any]], key: str) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in items:
        item_key = item.get(key)
        if item_key is None:
            continue
        grouped[str(item_key)].append(item)
    return dict(grouped)


def _build_candidate_targets(
    current_argument: dict[str, Any],
    arguments_by_id: dict[str, dict[str, Any]],
    turn_order: dict[str, int],
    turns_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    current_turn_order = turn_order.get(current_argument["turn_id"], 0)
    current_side = turns_by_id[current_argument["turn_id"]].get("side")
    candidates: list[dict[str, Any]] = []

    for argument in arguments_by_id.values():
        argument_turn_id = argument["turn_id"]
        argument_turn = turns_by_id.get(argument_turn_id)
        if argument_turn is None:
            continue
        if argument_turn.get("side") == current_side:
            continue
        if turn_order.get(argument_turn_id, 0) >= current_turn_order:
            continue
        candidates.append(
            {
                "argument_id": argument["argument_id"],
                "turn_id": argument_turn_id,
                "phase": argument_turn.get("phase"),
                "speaker_label": argument_turn.get("speaker_label"),
                "claim": argument.get("claim"),
            }
        )

    return candidates


def _infer_turn_difficulty(task_type: str, phase: str, item_count: int) -> str:
    hard_phases = {"cross_examination", "crossfire", "moderator_qna", "free_debate", "free_speech", "summary"}
    medium_phases = {"rebuttal", "closing", "opening", "constructive"}

    if task_type == "clash_identification":
        return "hard"
    if phase in hard_phases or item_count >= 3:
        return "hard"
    if phase in medium_phases or item_count == 2:
        return "medium"
    return "easy"