from __future__ import annotations

import os
import secrets


def load_api_keys() -> set[str]:
    """Load valid API keys from environment variable.

    API keys are comma-separated in the API_KEYS env var.
    If no keys are configured, authentication is disabled.
    """
    raw = os.getenv("API_KEYS", "").strip()
    if not raw:
        return set()
    return {key.strip() for key in raw.split(",") if key.strip()}


def generate_api_key() -> str:
    """Generate a new random API key."""
    return f"dp_{secrets.token_hex(24)}"


def check_api_key(provided_key: str | None, valid_keys: set[str]) -> bool:
    """Verify an API key against the valid set.

    Returns True if:
    - valid_keys is empty (auth disabled)
    - provided_key matches a valid key using constant-time comparison
    """
    if not valid_keys:
        return True
    if not provided_key:
        return False
    for valid_key in valid_keys:
        if secrets.compare_digest(provided_key, valid_key):
            return True
    return False
