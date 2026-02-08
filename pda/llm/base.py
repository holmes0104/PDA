"""Abstract LLM provider protocol."""

from typing import Any, Protocol, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class LLMProvider(Protocol):
    """Protocol for LLM backends (OpenAI, Anthropic)."""

    def complete(self, prompt: str, **kwargs: Any) -> str:
        """Return raw text completion."""
        ...

    def complete_structured(self, prompt: str, schema: type[BaseModel], **kwargs: Any) -> BaseModel:
        """Return completion parsed into the given Pydantic model (JSON)."""
        ...
