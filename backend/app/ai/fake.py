"""A provider that answers from a script.

Every AI test in the suite runs through this, which is what makes them
deterministic and free. It is also how the pipeline's retry and validation paths
are exercised at all — a real model cannot be asked to return bad SQL on demand.
"""

from pydantic import BaseModel

from app.ai.provider import ProviderUnavailable, T


class FakeProvider:
    def __init__(
        self,
        responses: list[BaseModel] | None = None,
        *,
        unavailable: bool = False,
    ) -> None:
        self.responses = list(responses or [])
        self.unavailable = unavailable
        self.prompts: list[str] = []

    async def generate(self, prompt: str, *, schema: type[T]) -> T:
        self.prompts.append(prompt)
        if self.unavailable:
            raise ProviderUnavailable("The fake provider is switched off.")
        if not self.responses:
            raise AssertionError("FakeProvider ran out of scripted responses")
        answer = self.responses.pop(0)
        assert isinstance(answer, schema), (
            f"scripted a {type(answer).__name__} where {schema.__name__} was asked for"
        )
        return answer
