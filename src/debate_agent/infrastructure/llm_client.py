from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Iterator

from openai import APIConnectionError, APITimeoutError, RateLimitError

from openai import OpenAI

from debate_agent.infrastructure.settings import Settings

logger = logging.getLogger(__name__)

_RETRYABLE_ERRORS = (RateLimitError, APIConnectionError, APITimeoutError)

_DEFAULT_MAX_RETRIES = 3
_DEFAULT_BASE_DELAY = 1.0


@dataclass(frozen=True, slots=True)
class LLMResponse:
    content: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class DebateLLMClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = OpenAI(
            api_key=settings.api_key,
            base_url=settings.base_url,
            timeout=settings.timeout_seconds,
        )
        self._max_retries = getattr(settings, "llm_max_retries", _DEFAULT_MAX_RETRIES) or _DEFAULT_MAX_RETRIES

    def generate_json(self, prompt: str, model: str | None = None) -> LLMResponse:
        resolved_model = model or self.settings.model
        start_time = time.monotonic()
        for attempt in range(self._max_retries):
            try:
                response = self.client.chat.completions.create(
                    model=resolved_model,
                    response_format={"type": "json_object"},
                    messages=[
                        {
                            "role": "system",
                            "content": "你必须只返回一个有效 JSON 对象，不要输出 Markdown、代码块或额外解释。",
                        },
                        {
                            "role": "user",
                            "content": prompt,
                        },
                    ],
                )
                if not response.choices:
                    usage = getattr(response, "usage", None)
                    return LLMResponse(
                        content="{}",
                        model=response.model,
                        prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
                        completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
                        total_tokens=getattr(usage, "total_tokens", 0) or 0,
                    )
                message = response.choices[0].message.content or "{}"
                usage = getattr(response, "usage", None)
                prompt_tokens = getattr(usage, "prompt_tokens", 0) or 0
                completion_tokens = getattr(usage, "completion_tokens", 0) or 0
                total_tokens = getattr(usage, "total_tokens", 0) or 0
                elapsed_ms = int((time.monotonic() - start_time) * 1000)
                logger.info(
                    "LLM JSON call completed",
                    extra={
                        "model": response.model,
                        "latency_ms": elapsed_ms,
                        "attempt": attempt + 1,
                        "prompt_tokens": prompt_tokens,
                        "completion_tokens": completion_tokens,
                        "total_tokens": total_tokens,
                    },
                )
                return LLMResponse(
                    content=message,
                    model=response.model,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=total_tokens,
                )
            except _RETRYABLE_ERRORS as error:
                if attempt == self._max_retries - 1:
                    raise RuntimeError(f"LLM call failed after {self._max_retries} attempts: {error}") from error
                delay = _DEFAULT_BASE_DELAY * (2 ** attempt)
                logger.warning("LLM call attempt %d/%d failed: %s — retrying in %.1fs", attempt + 1, self._max_retries, type(error).__name__, delay)
                time.sleep(delay)

    def parse_json(self, prompt: str, model: str | None = None) -> tuple[dict[str, object], LLMResponse]:
        response = self.generate_json(prompt, model=model)
        try:
            payload = json.loads(response.content)
        except json.JSONDecodeError as error:
            raise RuntimeError(f"Model did not return valid JSON: {error}") from error
        if not isinstance(payload, dict):
            raise RuntimeError("Model response JSON must be an object.")
        return payload, response

    def generate_text_stream(self, prompt: str, model: str | None = None) -> Iterator[str]:
        resolved_model = model or self.settings.model
        for attempt in range(self._max_retries):
            try:
                stream = self.client.chat.completions.create(
                    model=resolved_model,
                    messages=[
                        {
                            "role": "system",
                            "content": "你必须直接输出正文内容，不要输出 Markdown、代码块或额外前缀。",
                        },
                        {
                            "role": "user",
                            "content": prompt,
                        },
                    ],
                    stream=True,
                )
                break
            except _RETRYABLE_ERRORS as error:
                if attempt == self._max_retries - 1:
                    raise RuntimeError(f"LLM stream failed after {self._max_retries} attempts: {error}") from error
                delay = _DEFAULT_BASE_DELAY * (2 ** attempt)
                logger.warning("LLM stream attempt %d/%d failed: %s — retrying in %.1fs", attempt + 1, self._max_retries, type(error).__name__, delay)
                time.sleep(delay)
        else:
            return

        try:
            for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta.content or ""
                if delta:
                    yield delta
        except Exception as error:  # pragma: no cover - upstream client failure
            raise RuntimeError(f"Model stream interrupted: {error}") from error
