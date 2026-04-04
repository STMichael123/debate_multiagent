from __future__ import annotations

import json
import logging
import time

from debate_agent.infrastructure.exceptions import (
    DebateProjectError,
    InvalidInputError,
    LLMGenerationError,
    RateLimitExceededError,
    SessionNotFoundError,
)
from debate_agent.infrastructure.logging_config import JSONFormatter, configure_logging
from debate_agent.infrastructure.rate_limiter import InMemoryRateLimiter


# --- Rate Limiter Tests ---


class TestInMemoryRateLimiter:
    def test_allows_requests_within_limit(self):
        limiter = InMemoryRateLimiter(max_requests=3, window_seconds=60.0)
        assert limiter.is_allowed("user1") is True
        assert limiter.is_allowed("user1") is True
        assert limiter.is_allowed("user1") is True

    def test_blocks_requests_over_limit(self):
        limiter = InMemoryRateLimiter(max_requests=2, window_seconds=60.0)
        limiter.is_allowed("user1")
        limiter.is_allowed("user1")
        assert limiter.is_allowed("user1") is False

    def test_independent_keys(self):
        limiter = InMemoryRateLimiter(max_requests=1, window_seconds=60.0)
        assert limiter.is_allowed("user1") is True
        assert limiter.is_allowed("user2") is True
        assert limiter.is_allowed("user1") is False

    def test_cleanup_removes_stale_buckets(self):
        limiter = InMemoryRateLimiter(max_requests=5, window_seconds=0.01)
        limiter.is_allowed("stale_user")
        time.sleep(0.02)
        limiter.cleanup(max_age_seconds=0.01)
        assert "stale_user" not in limiter._buckets

    def test_window_expiry_allows_new_requests(self):
        limiter = InMemoryRateLimiter(max_requests=1, window_seconds=0.05)
        limiter.is_allowed("user1")
        assert limiter.is_allowed("user1") is False
        time.sleep(0.06)
        assert limiter.is_allowed("user1") is True


# --- Exceptions Tests ---


class TestExceptions:
    def test_base_exception(self):
        err = DebateProjectError("test")
        assert str(err) == "test"
        assert isinstance(err, Exception)

    def test_session_not_found(self):
        err = SessionNotFoundError("abc-123")
        assert err.session_id == "abc-123"
        assert "abc-123" in str(err)
        assert isinstance(err, DebateProjectError)

    def test_invalid_input(self):
        err = InvalidInputError("bad value")
        assert "bad value" in str(err)
        assert isinstance(err, DebateProjectError)

    def test_llm_generation_error(self):
        err = LLMGenerationError("api failed")
        assert isinstance(err, DebateProjectError)

    def test_rate_limit_exceeded(self):
        err = RateLimitExceededError()
        assert isinstance(err, DebateProjectError)

    def test_hierarchy(self):
        assert issubclass(SessionNotFoundError, DebateProjectError)
        assert issubclass(InvalidInputError, DebateProjectError)
        assert issubclass(LLMGenerationError, DebateProjectError)
        assert issubclass(RateLimitExceededError, DebateProjectError)


# --- Logging Config Tests ---


class TestJSONFormatter:
    def test_formats_basic_record(self):
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="hello world",
            args=(),
            exc_info=None,
        )
        output = formatter.format(record)
        parsed = json.loads(output)
        assert parsed["message"] == "hello world"
        assert parsed["level"] == "INFO"
        assert parsed["logger"] == "test.logger"
        assert "timestamp" in parsed

    def test_includes_extra_fields(self):
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="test",
            args=(),
            exc_info=None,
        )
        record.session_id = "sess-123"
        record.model = "gpt-4"
        record.latency_ms = 500
        output = formatter.format(record)
        parsed = json.loads(output)
        assert parsed["session_id"] == "sess-123"
        assert parsed["model"] == "gpt-4"
        assert parsed["latency_ms"] == 500

    def test_configure_logging_sets_handler(self):
        root = logging.getLogger()
        original_handlers = list(root.handlers)
        configure_logging(debug=True)
        assert any(isinstance(h.formatter, JSONFormatter) for h in root.handlers)
        assert root.level == logging.DEBUG
        root.handlers = original_handlers
