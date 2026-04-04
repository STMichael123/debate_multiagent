from __future__ import annotations

from debate_agent.domain.models import DebateSession, EvidenceRecord
from debate_agent.infrastructure.llm_client import DebateLLMClient
from debate_agent.orchestration.agent_services import ClosingAgent, CoachAgent, DebateAndFreeDebateAgent, InquiryAgent, MasterOrchestratorAgent, OpeningAgent, OpeningCoachAgent, OpponentAgent, SpeechAndClosingAgent, TurnAnalyzer
from debate_agent.orchestration.oversight import MatchTimerAutomation, OversightCoordinator
from debate_agent.orchestration.session_state import SessionStateMutator
from debate_agent.retrieval.evidence_service import EvidenceService
from debate_agent.retrieval.example_bank import ExampleBank
from debate_agent.retrieval.web_search import WebSearchRetriever


class PipelineRuntime:
    def __init__(self, llm_client: DebateLLMClient | None = None, enable_web_search: bool | None = None) -> None:
        self.llm_client = llm_client
        web_search_enabled = llm_client.settings.web_search_enabled if llm_client else True
        if enable_web_search is not None:
            web_search_enabled = enable_web_search
        web_search_limit = llm_client.settings.web_search_limit if llm_client else 3
        web_retriever = WebSearchRetriever(enabled=web_search_enabled)
        self.evidence_service = EvidenceService(
            web_retriever=web_retriever,
            default_limit=web_search_limit + 2,
        )
        self.state_mutator = SessionStateMutator()
        self.turn_analyzer = TurnAnalyzer(llm_client=llm_client)
        opponent_model = llm_client.settings.opponent_model if llm_client else None
        coach_model = llm_client.settings.coach_model if llm_client else None
        closing_model = llm_client.settings.closing_model if llm_client else None
        opening_model = llm_client.settings.model if llm_client else None
        self.example_bank = ExampleBank()
        self.master_agent = MasterOrchestratorAgent()
        self.opponent_agent = OpponentAgent(llm_client=llm_client, model_name=opponent_model, example_bank=self.example_bank)
        self.coach_agent = CoachAgent(llm_client=llm_client, model_name=coach_model, example_bank=self.example_bank)
        self.closing_agent = ClosingAgent(llm_client=llm_client, model_name=closing_model)
        self.opening_agent = OpeningAgent(llm_client=llm_client, model_name=opening_model)
        self.opening_coach_agent = OpeningCoachAgent(llm_client=llm_client, model_name=coach_model)
        self.inquiry_agent = InquiryAgent(llm_client=llm_client, model_name=opponent_model)
        self.debate_match_agent = DebateAndFreeDebateAgent(turn_analyzer=self.turn_analyzer, opponent_agent=self.opponent_agent)
        self.speech_match_agent = SpeechAndClosingAgent(opening_agent=self.opening_agent, closing_agent=self.closing_agent)
        self.oversight_coordinator = OversightCoordinator(
            coach_agent=self.coach_agent,
            opening_coach_agent=self.opening_coach_agent,
            timer_automation=MatchTimerAutomation(),
        )

    def latest_preparation_evidence(self, session: DebateSession) -> list[EvidenceRecord]:
        if not session.preparation_packets:
            return []
        return session.preparation_packets[-1].evidence_records

    def merge_upstream_evidence(self, session: DebateSession, live_records: list[EvidenceRecord]) -> list[EvidenceRecord]:
        merged: list[EvidenceRecord] = []
        seen: set[str] = set()
        for record in [*self.latest_preparation_evidence(session), *live_records]:
            dedupe_key = f"{record.evidence_id}|{record.source_ref}|{record.title}|{record.snippet}"
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            merged.append(record)
        return merged

    def retrieve_opening_evidence(self, session: DebateSession) -> tuple[list[EvidenceRecord], str | None]:
        evidence_result = self.evidence_service.retrieve(
            topic=session.topic,
            latest_user_turn=session.topic,
            clash_points=session.clash_points,
            limit=3 if not session.options.web_search_enabled else None,
            enable_web_search=session.options.web_search_enabled,
        )
        return self.merge_upstream_evidence(session, evidence_result.records), evidence_result.research_query

    def resolve_session_speaker(self, session: DebateSession, speaker_side: str | None, default_side: str = "user") -> str:
        requested_speaker = speaker_side or default_side
        return session.user_side if requested_speaker in {"user", "me", session.user_side} else session.agent_side

    def resolve_opening_speaker(self, session: DebateSession, speaker_side: str | None) -> str:
        return self.resolve_session_speaker(session, speaker_side, default_side="user")