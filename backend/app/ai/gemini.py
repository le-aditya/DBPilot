"""The Gemini provider. PRD section 8.

Structured output mode does the shape validation, so nothing here parses prose
looking for SQL. Every failure becomes ProviderUnavailable, because from the
pipeline's point of view a timeout, a quota refusal and a malformed answer all
mean the same thing: fall back to the editor and tell the user plainly.
"""

import asyncio
from typing import Any

from google import genai
from google.genai import types

from app.ai.provider import ProviderUnavailable, T
from app.core.config import get_settings


class GeminiProvider:
    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        settings = get_settings()
        key = api_key or settings.gemini_api_key
        if not key:
            raise ProviderUnavailable("No Gemini API key is configured.")
        self._client = genai.Client(api_key=key)
        self._model = model or settings.gemini_model
        self._timeout = settings.ai_timeout_seconds

    async def generate(self, prompt: str, *, schema: type[T]) -> T:
        config: dict[str, Any] = {
            "response_mime_type": "application/json",
            "response_schema": schema,
            # Deterministic on purpose: the same question against the same
            # schema should not produce different SQL run to run.
            "temperature": 0.0,
        }
        try:
            response = await asyncio.wait_for(
                self._client.aio.models.generate_content(
                    model=self._model,
                    contents=prompt,
                    config=types.GenerateContentConfig(**config),
                ),
                timeout=self._timeout,
            )
        except TimeoutError as error:
            raise ProviderUnavailable(
                f"The model did not answer within {self._timeout} seconds."
            ) from error
        except Exception as error:  # noqa: BLE001 — provider errors are all one case here
            raise ProviderUnavailable(f"The model could not be reached: {error}") from error

        parsed = getattr(response, "parsed", None)
        if isinstance(parsed, schema):
            return parsed
        text = getattr(response, "text", None)
        if text:
            try:
                return schema.model_validate_json(text)
            except Exception as error:  # noqa: BLE001
                raise ProviderUnavailable(
                    "The model returned something DBPilot could not read."
                ) from error
        raise ProviderUnavailable("The model returned an empty answer.")
