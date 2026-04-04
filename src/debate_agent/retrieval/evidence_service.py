from __future__ import annotations

from dataclasses import dataclass

from debate_agent.domain.models import ClashPoint, EvidenceRecord
from debate_agent.retrieval.local_dossier import LocalDossierRetriever
from debate_agent.retrieval.web_search import WebSearchRetriever


@dataclass(slots=True)
class EvidenceRetrievalResult:
    records: list[EvidenceRecord]
    research_query: str


class EvidenceService:
    def __init__(
        self,
        local_retriever: LocalDossierRetriever | None = None,
        web_retriever: WebSearchRetriever | None = None,
        default_limit: int = 5,
    ) -> None:
        self.local_retriever = local_retriever or LocalDossierRetriever()
        self.web_retriever = web_retriever or WebSearchRetriever(enabled=False)
        self.default_limit = default_limit

    def retrieve(
        self,
        topic: str,
        latest_user_turn: str = "",
        clash_points: list[ClashPoint] | None = None,
        limit: int | None = None,
        enable_web_search: bool = True,
    ) -> EvidenceRetrievalResult:
        effective_limit = max(1, limit or self.default_limit)
        local_records = self.local_retriever.retrieve(topic, limit=min(effective_limit, 3))
        research_queries = self._build_query_plan(topic, latest_user_turn, clash_points or [])

        remaining = max(0, effective_limit - len(local_records))
        web_records: list[EvidenceRecord] = []
        if enable_web_search and remaining > 0:
            for query in research_queries:
                query_limit = max(1, remaining)
                web_records.extend(self.web_retriever.retrieve(query, limit=query_limit))
                merged_preview = self._dedupe_records(local_records + web_records)
                remaining = max(0, effective_limit - len(merged_preview))
                if remaining <= 0:
                    break

        merged_records = self._sort_records(self._dedupe_records(local_records + web_records))
        return EvidenceRetrievalResult(records=merged_records[:effective_limit], research_query=" | ".join(research_queries))

    def _build_query_plan(self, topic: str, latest_user_turn: str, clash_points: list[ClashPoint]) -> list[str]:
        query_parts = [topic.strip()]
        if clash_points:
            query_parts.extend(item.topic_label.strip() for item in clash_points[:2] if item.topic_label.strip())
        if latest_user_turn.strip():
            query_parts.append(latest_user_turn.strip()[:80])
        base_query = " ".join(part for part in query_parts if part)
        return [
            f"{base_query} 官方 数据 统计 报告 研究",
            f"{base_query} 研究 理论 机制 学者 报告",
            f"{base_query} 真实案例 生活 场景 影响",
        ]

    def _dedupe_records(self, records: list[EvidenceRecord]) -> list[EvidenceRecord]:
        deduped: list[EvidenceRecord] = []
        seen: set[str] = set()
        for record in records:
            dedupe_key = f"{record.source_ref}|{record.title}|{record.snippet}"
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            deduped.append(record)
        return deduped

    def _sort_records(self, records: list[EvidenceRecord]) -> list[EvidenceRecord]:
        return sorted(
            records,
            key=lambda item: (
                item.credibility_score if item.credibility_score is not None else 0.0,
                item.relevance_score if item.relevance_score is not None else 0.0,
            ),
            reverse=True,
        )