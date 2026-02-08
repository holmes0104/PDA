"""Anthropic LLM implementation with structured output via tool use / JSON parse."""

import json
import re
from typing import Any

from anthropic import Anthropic
from pydantic import BaseModel

from pda.llm.base import LLMProvider


class AnthropicProvider:
    """Anthropic chat completion with optional structured (JSON) output."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "claude-3-5-sonnet-20241022",
    ):
        self._client = Anthropic(api_key=api_key)
        self._model = model

    def complete(self, prompt: str, **kwargs: Any) -> str:
        response = self._client.messages.create(
            model=kwargs.get("model") or self._model,
            max_tokens=kwargs.get("max_tokens", 4096),
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text if response.content else ""

    def complete_structured(self, prompt: str, schema: type[BaseModel], **kwargs: Any) -> BaseModel:
        instruction = (
            "Respond with a single JSON object that conforms to the schema. "
            "No markdown, no code fence, only raw JSON."
        )
        full_prompt = f"{prompt}\n\n{instruction}"
        raw = self.complete(full_prompt, **kwargs)
        # Strip possible markdown code block
        text = raw.strip()
        if text.startswith("```"):
            text = re.sub(r"^```\w*\n?", "", text)
            text = re.sub(r"\n?```\s*$", "", text)
        data = json.loads(text)
        return schema.model_validate(data)
