from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

from debate_agent.domain.models import EvidenceRecord


@dataclass(frozen=True, slots=True)
class Dossier:
    dossier_id: str
    topic: str
    aliases: list[str]
    evidence: list[dict[str, str]]


class LocalDossierRetriever:
    def __init__(self, dossier_dir: Path | None = None) -> None:
        self.dossier_dir = dossier_dir or self._default_dossier_dir()
        self._cached_dossiers: list[Dossier] | None = None

    def retrieve(self, topic: str, limit: int = 3) -> list[EvidenceRecord]:
        dossiers = self._load_dossiers()
        dossier = self._select_best_dossier(topic, dossiers)
        if dossier is None:
            return []

        records: list[EvidenceRecord] = []
        for item in dossier.evidence[:limit]:
            records.append(
                EvidenceRecord(
                    evidence_id=item["evidence_id"],
                    query_text=topic,
                    source_type=item.get("source_type", "dossier"),
                    source_ref=item.get("source_ref", f"dossier://{dossier.dossier_id}"),
                    title=item["title"],
                    snippet=item["snippet"],
                    stance_hint=item.get("stance_hint", ""),
                    relevance_score=self._score_match(topic, dossier),
                    credibility_score=0.75,
                    verification_state="curated",
                )
            )
        return records

    def _load_dossiers(self) -> list[Dossier]:
        if self._cached_dossiers is not None:
            return self._cached_dossiers

        if not self.dossier_dir.exists():
            return []

        dossiers: list[Dossier] = []
        for file_path in sorted(self.dossier_dir.glob("*.json")):
            try:
                payload = json.loads(file_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as error:
                logging.warning("Skipping invalid dossier file %s: %s", file_path.name, error)
                continue
            if not isinstance(payload, dict) or "dossier_id" not in payload or "topic" not in payload:
                logging.warning("Skipping malformed dossier file %s: missing required fields", file_path.name)
                continue
            dossiers.append(
                Dossier(
                    dossier_id=payload["dossier_id"],
                    topic=payload["topic"],
                    aliases=list(payload.get("aliases", [])),
                    evidence=list(payload.get("evidence", [])),
                )
            )
        self._cached_dossiers = dossiers
        return dossiers

    def _select_best_dossier(self, topic: str, dossiers: list[Dossier]) -> Dossier | None:
        if not dossiers:
            return None

        scored = sorted(
            ((self._score_match(topic, dossier), dossier) for dossier in dossiers),
            key=lambda item: item[0],
            reverse=True,
        )
        best_score, best_dossier = scored[0]
        return best_dossier if best_score > 0 else None

    def _score_match(self, topic: str, dossier: Dossier) -> float:
        normalized_topic = self._normalize(topic)
        candidates = [dossier.topic, *dossier.aliases]
        best_score = 0.0
        for candidate in candidates:
            normalized_candidate = self._normalize(candidate)
            if not normalized_candidate:
                continue
            if normalized_candidate in normalized_topic or normalized_topic in normalized_candidate:
                best_score = max(best_score, 1.0)
                continue
            overlap = set(normalized_topic) & set(normalized_candidate)
            score = len(overlap) / max(len(set(normalized_candidate)), 1)
            best_score = max(best_score, score)
        return best_score

    def _normalize(self, value: str) -> str:
        return "".join(value.lower().split())

    def _default_dossier_dir(self) -> Path:
        return Path(__file__).resolve().parents[3] / "data" / "dossiers"