from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from debate_agent.domain.models import EvidenceRecord


@dataclass(slots=True)
class AnnotatedArgument:
    argument_id: str
    claim: str
    warrant: str
    impact: str
    tags: list[str] = field(default_factory=list)
    confidence: str = "medium"


@dataclass(slots=True)
class DebateExample:
    """A single annotated example from a benchmark match."""
    case_id: str
    topic: str
    side: str
    phase: str
    speaker_label: str
    raw_excerpt: str
    normalized_text: str
    arguments: list[AnnotatedArgument] = field(default_factory=list)
    attack_type: str | None = None
    claim_role: str | None = None
    response_to_argument_ids: list[str] = field(default_factory=list)
    evidence_refs: list[dict[str, str]] = field(default_factory=list)


class ExampleBank:
    """Load and retrieve benchmark examples for few-shot prompt injection.

    Provides semantic matching of current debate context against a curated
    bank of annotated high-quality debate excerpts.
    """

    def __init__(self, benchmark_dir: Path | None = None) -> None:
        self.benchmark_dir = benchmark_dir or self._default_benchmark_dir()
        self._examples: list[DebateExample] = []
        self._by_attack_type: dict[str, list[DebateExample]] = {}
        self._by_claim_role: dict[str, list[DebateExample]] = {}
        self._loaded = False

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._load_all()
        self._loaded = True

    def _load_all(self) -> None:
        for seed_file in sorted(self.benchmark_dir.glob("seed_v*.json")):
            self._load_seed(seed_file)
        for ann_file in sorted(self.benchmark_dir.glob("benchmark_v*_annotations.json")):
            self._load_annotations(ann_file)

    def _load_seed(self, path: Path) -> None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return
        for case in data.get("cases", []):
            inp = case.get("input", {})
            gold = case.get("gold", {})
            arguments: list[AnnotatedArgument] = []
            for arg in gold.get("arguments", []):
                arguments.append(
                    AnnotatedArgument(
                        argument_id=arg.get("argument_id", ""),
                        claim=arg.get("claim", ""),
                        warrant=arg.get("warrant", ""),
                        impact=arg.get("impact", ""),
                        tags=arg.get("tags", []),
                        confidence=arg.get("confidence", "medium"),
                    )
                )
            evidence_refs = []
            for ev in gold.get("evidence", []):
                evidence_refs.append({
                    "title": ev.get("title", ""),
                    "source_ref": ev.get("source_ref", ""),
                    "use_purpose": ev.get("use_purpose", ""),
                })
            self._examples.append(
                DebateExample(
                    case_id=case.get("case_id", ""),
                    topic=inp.get("topic", ""),
                    side=inp.get("side", ""),
                    phase=inp.get("phase", ""),
                    speaker_label=inp.get("speaker_label", ""),
                    raw_excerpt=inp.get("raw_excerpt", ""),
                    normalized_text=inp.get("normalized_text", ""),
                    arguments=arguments,
                    evidence_refs=evidence_refs,
                )
            )

    def _load_annotations(self, path: Path) -> None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return
        annotation_map: dict[str, dict] = {}
        for arg_id, ann in data.get("argument_annotations", {}).items():
            annotation_map[arg_id] = ann
            attack_type = ann.get("attack_type")
            claim_role = ann.get("claim_role")
            if attack_type:
                self._by_attack_type.setdefault(attack_type, [])
            if claim_role:
                self._by_claim_role.setdefault(claim_role, [])
        for example in self._examples:
            for arg in example.arguments:
                ann = annotation_map.get(arg.argument_id)
                if ann is None:
                    continue
                if ann.get("attack_type"):
                    example.attack_type = ann["attack_type"]
                    self._by_attack_type.setdefault(ann["attack_type"], []).append(example)
                if ann.get("claim_role"):
                    example.claim_role = ann["claim_role"]
                    self._by_claim_role.setdefault(ann["claim_role"], []).append(example)
                if ann.get("response_to_argument_ids"):
                    example.response_to_argument_ids = ann["response_to_argument_ids"]

    def retrieve(
        self,
        task: str = "opponent_response",
        topic: str = "",
        phase: str = "",
        attack_type: str | None = None,
        limit: int = 3,
    ) -> list[DebateExample]:
        """Retrieve the most relevant examples for the current context."""
        self._ensure_loaded()
        candidates = self._examples

        if attack_type and attack_type in self._by_attack_type:
            candidates = self._by_attack_type[attack_type]

        scored: list[tuple[float, DebateExample]] = []
        topic_lower = topic.lower()
        for ex in candidates:
            score = 0.0
            if topic_lower and topic_lower in ex.topic.lower():
                score += 2.0
            if phase and phase in ex.phase:
                score += 1.0
            if ex.arguments:
                best_arg_confidence = max(
                    {"high": 3.0, "medium": 2.0, "low": 1.0}.get(a.confidence, 1.0)
                    for a in ex.arguments
                )
                score += best_arg_confidence
            if ex.raw_excerpt and len(ex.raw_excerpt) > 30:
                score += 0.5
            scored.append((score, ex))

        scored.sort(key=lambda x: x[0], reverse=True)
        seen_ids: set[str] = set()
        results: list[DebateExample] = []
        for _, ex in scored:
            if ex.case_id not in seen_ids:
                results.append(ex)
                seen_ids.add(ex.case_id)
            if len(results) >= limit:
                break
        return results

    def get_attack_types(self) -> list[str]:
        self._ensure_loaded()
        return sorted(self._by_attack_type.keys())

    def get_examples_by_attack(self, attack_type: str, limit: int = 2) -> list[DebateExample]:
        self._ensure_loaded()
        return self._by_attack_type.get(attack_type, [])[:limit]

    @property
    def total_examples(self) -> int:
        self._ensure_loaded()
        return len(self._examples)

    def _default_benchmark_dir(self) -> Path:
        return Path(__file__).resolve().parents[3] / "data" / "benchmarks"
