"""LLM adapter layer — OpenAI and Anthropic behind a common protocol."""

from pda.llm.anthropic_provider import AnthropicProvider
from pda.llm.base import LLMProvider
from pda.llm.openai_provider import OpenAIProvider


def get_provider(provider_name: str, **kwargs: object) -> LLMProvider:
    """Return the configured LLM provider. provider_name: 'openai' | 'anthropic'."""
    if provider_name.lower() == "anthropic":
        return AnthropicProvider(**kwargs)
    return OpenAIProvider(**kwargs)


__all__ = ["LLMProvider", "OpenAIProvider", "AnthropicProvider", "get_provider"]
