from __future__ import annotations

import unittest

from debate_agent.domain.models import EvidenceRecord
from debate_agent.prompts.builders import build_evidence_quality_summary, build_evidence_usage_guidance, format_evidence_packet
from debate_agent.retrieval import web_search
from debate_agent.retrieval.web_search import WebSearchRetriever, assess_web_source_quality


class EvidenceQualityTests(unittest.TestCase):
    def test_debate_repost_source_is_filtered_out(self) -> None:
        quality = assess_web_source_quality(
            title="辩之竹：人工智能教育一辩稿",
            snippet="这是一篇整理好的辩论稿与观点汇编。",
            source_ref="https://example.com/bianzhizhu/debate-script",
        )

        self.assertFalse(quality["is_usable"])
        self.assertEqual(quality["verification_state"], "filtered_low_quality")

    def test_evidence_guidance_requires_theory_and_scenario_fallback(self) -> None:
        guidance = build_evidence_usage_guidance([])

        self.assertIn("不要捏造数字", guidance)
        self.assertIn("学理机制", guidance)
        self.assertIn("生活情景", guidance)

    def test_evidence_packet_includes_source_authority(self) -> None:
        packet = format_evidence_packet(
            [
                EvidenceRecord(
                    evidence_id="web-1",
                    query_text="测试辩题",
                    source_type="web_search_authoritative",
                    source_ref="https://www.unesco.org/report",
                    title="UNESCO Report",
                    snippet="2024 年相关项目覆盖率达到 64%。",
                    credibility_score=0.85,
                    relevance_score=0.9,
                    verification_state="high_authority",
                )
            ]
        )

        summary = build_evidence_quality_summary(
            [
                EvidenceRecord(
                    evidence_id="web-1",
                    query_text="测试辩题",
                    source_type="web_search_authoritative",
                    source_ref="https://www.unesco.org/report",
                    title="UNESCO Report",
                    snippet="2024 年相关项目覆盖率达到 64%。",
                    credibility_score=0.85,
                    relevance_score=0.9,
                    verification_state="high_authority",
                )
            ]
        )

        self.assertIn("来源位阶=高", packet)
        self.assertIn("高效力数据=1", summary)

    def test_web_search_retriever_passes_timeout_when_supported(self) -> None:
        original_ddgs = web_search.DDGS

        class FakeDDGS:
            last_timeout = None

            def __init__(self, timeout=None):
                FakeDDGS.last_timeout = timeout

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def text(self, query, max_results=3):
                return []

        web_search.DDGS = FakeDDGS
        try:
            retriever = WebSearchRetriever(enabled=True, timeout_seconds=1.5)
            self.assertEqual(retriever.retrieve("测试辩题", limit=1), [])
            self.assertEqual(FakeDDGS.last_timeout, 1.5)
        finally:
            web_search.DDGS = original_ddgs

    def test_web_search_retriever_falls_back_when_timeout_not_supported(self) -> None:
        original_ddgs = web_search.DDGS

        class FakeDDGS:
            init_calls = 0

            def __init__(self, timeout=None):
                FakeDDGS.init_calls += 1
                if timeout is not None:
                    raise TypeError("timeout not supported")

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def text(self, query, max_results=3):
                return []

        web_search.DDGS = FakeDDGS
        try:
            retriever = WebSearchRetriever(enabled=True, timeout_seconds=2.0)
            self.assertEqual(retriever.retrieve("测试辩题", limit=1), [])
            self.assertEqual(FakeDDGS.init_calls, 2)
        finally:
            web_search.DDGS = original_ddgs


if __name__ == "__main__":
    unittest.main()