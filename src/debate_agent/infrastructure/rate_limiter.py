from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field


@dataclass(slots=True)
class _SlidingWindow:
    timestamps: list[float] = field(default_factory=list)


class InMemoryRateLimiter:
    """Lightweight per-IP sliding window rate limiter."""

    def __init__(self, max_requests: int = 30, window_seconds: float = 60.0) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._buckets: dict[str, _SlidingWindow] = defaultdict(_SlidingWindow)

    def is_allowed(self, key: str) -> bool:
        now = time.monotonic()
        bucket = self._buckets[key]
        cutoff = now - self.window_seconds
        bucket.timestamps = [ts for ts in bucket.timestamps if ts > cutoff]
        if len(bucket.timestamps) >= self.max_requests:
            return False
        bucket.timestamps.append(now)
        return True

    def cleanup(self, max_age_seconds: float = 300.0) -> None:
        """Remove stale buckets to prevent unbounded memory growth."""
        now = time.monotonic()
        stale_keys = [
            key
            for key, bucket in self._buckets.items()
            if not bucket.timestamps or bucket.timestamps[-1] < now - max_age_seconds
        ]
        for key in stale_keys:
            del self._buckets[key]
