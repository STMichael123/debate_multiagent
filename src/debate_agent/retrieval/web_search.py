from __future__ import annotations

import hashlib
import logging
from urllib.parse import urlparse

from debate_agent.domain.models import EvidenceRecord

try:
    from ddgs import DDGS
except ImportError:  # pragma: no cover - optional dependency handled at runtime
    try:
        from duckduckgo_search import DDGS
    except ImportError:
        DDGS = None  # type: ignore[assignment]


class WebSearchRetriever:
    def __init__(self, enabled: bool = True, timeout_seconds: float = 2.0) -> None:
        self.enabled = enabled
        self.timeout_seconds = max(0.5, timeout_seconds)

    def retrieve(self, query: str, limit: int = 3) -> list[EvidenceRecord]:
        if not self.enabled or DDGS is None or not query.strip() or limit <= 0:
            return []

        try:
            with self._create_search_client() as search_client:
                raw_results = list(search_client.text(query, max_results=limit))
        except Exception:
            logging.warning("Web search failed for query: %s", query[:80], exc_info=True)
            return []

        records: list[EvidenceRecord] = []
        for index, item in enumerate(raw_results[:limit], start=1):
            if not isinstance(item, dict):
                continue
            title = _ensure_str(item.get("title"), default=f"网页资料 {index}")
            snippet = _ensure_str(item.get("body")) or _ensure_str(item.get("snippet"))
            source_ref = _ensure_str(item.get("href")) or _ensure_str(item.get("url")) or f"web://result/{index}"
            if not title or not snippet:
                continue

            quality = assess_web_source_quality(title=title, snippet=snippet, source_ref=source_ref)
            if not quality["is_usable"]:
                continue

            hash_source = f"{query}|{source_ref}|{title}"
            evidence_id = f"web-{hashlib.md5(hash_source.encode('utf-8')).hexdigest()[:10]}"
            records.append(
                EvidenceRecord(
                    evidence_id=evidence_id,
                    query_text=query,
                    source_type=quality["source_type"],
                    source_ref=source_ref,
                    title=title,
                    snippet=snippet,
                    relevance_score=max(0.35, 1.0 - (index - 1) * 0.1),
                    credibility_score=quality["credibility_score"],
                    verification_state=quality["verification_state"],
                )
            )
        return records

    def _create_search_client(self):
        try:
            return DDGS(timeout=self.timeout_seconds)
        except TypeError:
            return DDGS()


def assess_web_source_quality(title: str, snippet: str, source_ref: str) -> dict[str, object]:
    normalized_title = title.lower()
    normalized_snippet = snippet.lower()
    normalized_ref = source_ref.lower()
    host = urlparse(source_ref).netloc.lower()
    combined_text = " ".join([normalized_title, normalized_snippet, normalized_ref])

    if _looks_like_debate_repost(combined_text, host):
        return {
            "is_usable": False,
            "credibility_score": 0.1,
            "verification_state": "filtered_low_quality",
            "source_type": "web_search_filtered",
        }

    authority_score = 0.42
    verification_state = "source_screened"
    source_type = "web_search_screened"

    if _is_high_authority_host(host):
        authority_score = 0.85
        verification_state = "high_authority"
        source_type = "web_search_authoritative"
    elif _looks_like_research_source(combined_text, host):
        authority_score = 0.72
        verification_state = "research_backed"
        source_type = "web_search_research"
    elif _looks_like_news_or_institutional_source(host):
        authority_score = 0.6
        verification_state = "institutional_reporting"
        source_type = "web_search_institutional"

    return {
        "is_usable": authority_score >= 0.55,
        "credibility_score": authority_score,
        "verification_state": verification_state,
        "source_type": source_type,
    }


LOW_VALUE_KEYWORDS = [
    "辩论",
    "辩题",
    "一辩稿",
    "二辩稿",
    "三辩稿",
    "四辩稿",
    "攻辩",
    "立论稿",
    "辩词",
    "稿件",
    "辩之竹",
    "知乎",
    "贴吧",
    "论坛",
    "blog",
    "bbs",
    "wenku",
    "docin",
    "doc88",
    "360doc",
]

LOW_VALUE_HOSTS = {
    "zhihu.com",
    "www.zhihu.com",
    "tieba.baidu.com",
    "wenku.baidu.com",
    "www.docin.com",
    "www.doc88.com",
    "www.360doc.com",
    "www.bilibili.com",
}


def _looks_like_debate_repost(text: str, host: str) -> bool:
    return host in LOW_VALUE_HOSTS or any(keyword in text for keyword in LOW_VALUE_KEYWORDS)


HIGH_AUTHORITY_SUFFIXES = (".gov", ".gov.cn", ".edu", ".edu.cn", ".ac.uk")
HIGH_AUTHORITY_HOSTS = {
    "www.oecd.org",
    "www.unesco.org",
    "www.unicef.org",
    "www.worldbank.org",
    "www.who.int",
    "www.imf.org",
}


def _is_high_authority_host(host: str) -> bool:
    return host.endswith(HIGH_AUTHORITY_SUFFIXES) or host in HIGH_AUTHORITY_HOSTS


RESEARCH_KEYWORDS = [
    "research",
    "study",
    "journal",
    "paper",
    "report",
    "研究",
    "论文",
    "期刊",
    "报告",
    "大学",
    "研究院",
]
RESEARCH_HOST_SUFFIXES = (".org", ".edu", ".ac.uk")


def _looks_like_research_source(text: str, host: str) -> bool:
    return any(keyword in text for keyword in RESEARCH_KEYWORDS) or host.endswith(RESEARCH_HOST_SUFFIXES)


INSTITUTIONAL_HOST_SUFFIXES = (
    ".org",
    ".int",
    ".news",
    ".cn",
)
TRUSTED_NEWS_HOSTS = {
    "www.bbc.com",
    "www.reuters.com",
    "apnews.com",
    "www.nytimes.com",
    "www.theguardian.com",
    "www.people.com.cn",
    "www.xinhuanet.com",
}


def _looks_like_news_or_institutional_source(host: str) -> bool:
    return host in TRUSTED_NEWS_HOSTS or host.endswith(INSTITUTIONAL_HOST_SUFFIXES)


def _ensure_str(value: object, default: str = "") -> str:
    if isinstance(value, str):
        return value.strip()
    if value is None:
        return default
    return str(value).strip() or default