from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True, slots=True)
class Settings:
    api_key: str
    base_url: str
    model: str
    timeout_seconds: float = 90.0
    opponent_model: str | None = None
    coach_model: str | None = None
    closing_model: str | None = None
    web_search_enabled: bool = True
    web_search_limit: int = 3
    cors_allowed_origins: list[str] | None = None
    llm_max_retries: int = 3
    app_env: str = "development"
    debug: bool = True
    session_store_type: str = "json"
    database_url: str = ""


def is_production() -> bool:
    return os.getenv("APP_ENV", "development").strip().lower() == "production"


def load_settings() -> Settings:
    load_dotenv()
    app_env = os.getenv("APP_ENV", "development").strip().lower()
    debug = app_env != "production"
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").strip()
    model = os.getenv("OPENAI_MODEL", "gpt-5.4").strip()
    timeout_raw = os.getenv("OPENAI_TIMEOUT_SECONDS", "90").strip()
    opponent_model = os.getenv("OPENAI_OPPONENT_MODEL", "").strip() or model
    coach_model = os.getenv("OPENAI_COACH_MODEL", "").strip() or model
    closing_model = os.getenv("OPENAI_CLOSING_MODEL", "").strip() or model
    web_search_enabled = _read_bool_env("WEB_SEARCH_ENABLED", default=True)
    web_search_limit = _read_positive_int_env("WEB_SEARCH_LIMIT", default=3)

    cors_raw = os.getenv("CORS_ALLOWED_ORIGINS", "").strip()
    cors_allowed_origins: list[str] | None = None
    if cors_raw:
        cors_allowed_origins = [origin.strip() for origin in cors_raw.split(",") if origin.strip()]

    llm_max_retries = _read_positive_int_env("LLM_MAX_RETRIES", default=3)
    session_store_type = os.getenv("SESSION_STORE_TYPE", "json").strip().lower()
    database_url = os.getenv("DATABASE_URL", "").strip()

    if not api_key:
        raise RuntimeError("Missing OPENAI_API_KEY. Add it to the local environment or .env file.")

    if app_env == "production" and cors_allowed_origins is None:
        import warnings
        warnings.warn(
            "Running in production without CORS_ALLOWED_ORIGINS — all origins are allowed. "
            "Set CORS_ALLOWED_ORIGINS to restrict access.",
            stacklevel=2,
        )

    if not model:
        raise RuntimeError("Missing OPENAI_MODEL. Add it to the local environment or .env file.")

    timeout_seconds = float(timeout_raw or "90")
    if timeout_seconds <= 0:
        raise RuntimeError("OPENAI_TIMEOUT_SECONDS must be greater than 0.")

    return Settings(
        api_key=api_key,
        base_url=base_url,
        model=model,
        timeout_seconds=timeout_seconds,
        opponent_model=opponent_model,
        coach_model=coach_model,
        closing_model=closing_model,
        web_search_enabled=web_search_enabled,
        web_search_limit=web_search_limit,
        cors_allowed_origins=cors_allowed_origins,
        llm_max_retries=llm_max_retries,
        app_env=app_env,
        debug=debug,
        session_store_type=session_store_type,
        database_url=database_url,
    )


def _read_bool_env(name: str, default: bool) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() not in {"0", "false", "no", "off"}


def _read_positive_int_env(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None or not raw_value.strip():
        return default
    try:
        parsed = int(raw_value)
    except ValueError as error:
        raise RuntimeError(f"{name} must be an integer.") from error
    if parsed < 0:
        raise RuntimeError(f"{name} must be greater than or equal to 0.")
    return parsed