"""Provider wiring, kept out of api/deps.py so the auth seam stays about auth."""

from app.ai.gemini import GeminiProvider
from app.ai.provider import LLMProvider, ProviderUnavailable
from app.core.config import get_settings

_provider: LLMProvider | None = None


def get_provider() -> LLMProvider:
    """The process-wide provider. Overridden in tests with the fake."""
    global _provider
    if _provider is None:
        if not get_settings().gemini_api_key:
            raise ProviderUnavailable(
                "AI is not configured on this server. You can still write SQL yourself."
            )
        _provider = GeminiProvider()
    return _provider


def set_provider(provider: LLMProvider | None) -> None:
    global _provider
    _provider = provider
