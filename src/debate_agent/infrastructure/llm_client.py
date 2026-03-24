from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Iterator

from openai import OpenAI

from debate_agent.infrastructure.settings import Settings


@dataclass(frozen=True, slots=True)
class LLMResponse:
    content: str
    model: str


class DebateLLMClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = OpenAI(
            api_key=settings.api_key,
            base_url=settings.base_url,
            timeout=settings.timeout_seconds,
        )

    def generate_json(self, prompt: str, model: str | None = None) -> LLMResponse:
        response = self.client.chat.completions.create(
            model=model or self.settings.model,
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
        message = response.choices[0].message.content or "{}"
        return LLMResponse(content=message, model=response.model)

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
        try:
            stream = self.client.chat.completions.create(
                model=model or self.settings.model,
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
        except Exception as error:  # pragma: no cover - upstream client failure
            raise RuntimeError(f"Model stream failed to start: {error}") from error

        try:
            for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta.content or ""
                if delta:
                    yield delta
        except Exception as error:  # pragma: no cover - upstream client failure
            raise RuntimeError(f"Model stream interrupted: {error}") from error