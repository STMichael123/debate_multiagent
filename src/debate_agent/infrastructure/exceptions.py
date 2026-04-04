from __future__ import annotations


class DebateProjectError(Exception):
    """Base exception for all debate-project errors."""


class LLMGenerationError(DebateProjectError):
    """Raised when an LLM API call fails after all retries."""


class SessionNotFoundError(DebateProjectError):
    """Raised when a requested session does not exist."""

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        super().__init__(f"Session not found: {session_id}")


class InvalidInputError(DebateProjectError):
    """Raised when user input fails validation."""

    def __init__(self, message: str) -> None:
        super().__init__(message)


class RateLimitExceededError(DebateProjectError):
    """Raised when the client has exceeded the allowed request rate."""
