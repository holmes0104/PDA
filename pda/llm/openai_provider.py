"""OpenAI LLM implementation with structured output via JSON in prompt."""

import json
import re
from typing import Any

from openai import APIError, APIStatusError, OpenAI, RateLimitError
from pydantic import BaseModel

from pda.llm.base import LLMProvider


class OpenAIProvider:
    """OpenAI chat completion with optional structured (JSON) output."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "gpt-5.2",
    ):
        self._client = OpenAI(api_key=api_key)
        self._model = model

    def complete(self, prompt: str, **kwargs: Any) -> str:
        try:
            response = self._client.chat.completions.create(
                model=kwargs.get("model") or self._model,
                messages=[{"role": "user", "content": prompt}],
                **{k: v for k, v in kwargs.items() if k not in ("model",)},
            )
            msg = response.choices[0].message
            return msg.content or ""
        except (RateLimitError, APIStatusError, APIError) as e:
            # Re-raise OpenAI exceptions as-is so they can be caught by route handlers
            # The route handlers will check status_code and error messages
            raise

    def complete_structured(self, prompt: str, schema: type[BaseModel], **kwargs: Any) -> BaseModel:
        instruction = (
            "Respond with a single JSON object only. No markdown, no code fence, no explanation."
        )
        full_prompt = f"{prompt}\n\n{instruction}"
        raw = self.complete(full_prompt, **kwargs)
        text = raw.strip()
        if text.startswith("```"):
            text = re.sub(r"^```\w*\n?", "", text)
            text = re.sub(r"\n?```\s*$", "", text)
        data = json.loads(text)
        return schema.model_validate(data)
