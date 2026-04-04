from __future__ import annotations

from pathlib import Path
from typing import Protocol

from debate_agent.domain.models import DebateSession


class SessionStore(Protocol):
    """Abstract interface for session persistence."""

    def save_session(self, session: DebateSession) -> Path: ...
    def load_session(self, session_id: str) -> DebateSession: ...
    def list_session_ids(self) -> list[str]: ...
    def delete_session(self, session_id: str) -> Path: ...
