"""The Gemini provider. PRD section 8.

Structured output mode does the shape validation, so nothing here parses prose
looking for SQL. Every failure becomes ProviderUnavailable, because from the
pipeline's point of view a timeout, a quota refusal and a malformed answer all
mean the same thing: fall back to the editor and tell the user plainly.
"""

import asyncio
import random
import time
from typing import Any

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from app.ai.provider import ProviderUnavailable, T
from app.core.config import get_settings


def _brief(error: genai_errors.APIError) -> str:
    """The provider's message without the JSON envelope the user cannot act on."""
    message = getattr(error, "message", None) or str(error)
    return str(message).splitlines()[0][:200]


class GeminiProvider:
    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        settings = get_settings()
        key = api_key or settings.gemini_api_key
        if not key:
            raise ProviderUnavailable("No Gemini API key is configured.")
        self._client = genai.Client(api_key=key)
        self._model = model or settings.gemini_model
        self._timeout = settings.ai_timeout_seconds

    # Google returns these when the model is momentarily overloaded or the key
    # is being rate limited. Both clear on their own, so a first attempt failing
    # should not become a visible outage.
    _TRANSIENT = frozenset({429, 500, 502, 503, 504})
    _ATTEMPTS = 3

    async def generate(self, prompt: str, *, schema: type[T]) -> T:
        config: dict[str, Any] = {
            "response_mime_type": "application/json",
            "response_schema": schema,
            # Deterministic on purpose: the same question against the same
            # schema should not produce different SQL run to run.
            "temperature": 0.0,
        }
        # One deadline for the whole call, retries included: PRD section 9
        # budgets the round trip, so three attempts must not become three
        # times the wait the user was promised.
        deadline = time.monotonic() + self._timeout
        response = None
        last: Exception | None = None
        for attempt in range(self._ATTEMPTS):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            try:
                response = await asyncio.wait_for(
                    self._client.aio.models.generate_content(
                        model=self._model,
                        contents=prompt,
                        config=types.GenerateContentConfig(**config),
                    ),
                    timeout=remaining,
                )
                break
            except TimeoutError as error:
                # Retried, not fatal: an overloaded model hangs as often as it
                # returns 503, and a hang on the first attempt is not an outage.
                last = error
                if attempt == self._ATTEMPTS - 1 or time.monotonic() >= deadline:
                    raise ProviderUnavailable(
                        f"The model did not answer within {self._timeout} seconds."
                    ) from error
                await asyncio.sleep((2**attempt) * 0.5 + random.random() * 0.3)
            except genai_errors.APIError as error:
                last = error
                if error.code not in self._TRANSIENT or attempt == self._ATTEMPTS - 1:
                    raise ProviderUnavailable(
                        f"The model could not be reached: {_brief(error)}"
                    ) from error
                # Exponential backoff with jitter, so concurrent users do not
                # retry in lockstep and re-create the overload they are waiting on.
                await asyncio.sleep((2**attempt) * 0.5 + random.random() * 0.3)
            except Exception as error:  # noqa: BLE001 — every other failure is one case
                raise ProviderUnavailable(
                    f"The model could not be reached: {error}"
                ) from error
        else:  # pragma: no cover — the loop breaks or raises first
            raise ProviderUnavailable(f"The model could not be reached: {last}")

        if response is None:
            raise ProviderUnavailable(
                f"The model did not answer within {self._timeout} seconds."
            )

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
