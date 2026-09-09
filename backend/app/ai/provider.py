"""The seam between DBPilot and whichever model is answering.

This protocol is the concrete mitigation for the PRD section 13 outage risk: the
pipeline depends on the protocol, so a provider that is down, rate limited or
not configured degrades to a clear error with the SQL editor still usable,
rather than taking the feature out.
"""

from typing import Protocol, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class ProviderUnavailable(Exception):
    """The model could not be reached, or is not configured."""


class LLMProvider(Protocol):
    async def generate(self, prompt: str, *, schema: type[T]) -> T:
        """Return a `schema` instance built from the model's structured output."""
        ...
