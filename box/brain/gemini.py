"""Gemini, called directly from the box with a Google AI Studio key (see llm.py for where keys live).

Brief overloads (429/5xx) are retried once, then the next model in the list is tried.
"""

import base64
import time
from typing import TypeVar

from google import genai
from google.genai import errors, types
from pydantic import BaseModel

from .llm import Image

T = TypeVar("T", bound=BaseModel)


class Gemini:
    def __init__(self, key: str, timeout_s: float = 30.0):
        self.client = genai.Client(api_key=key, http_options=types.HttpOptions(timeout=int(timeout_s * 1000)))
        self.calls = 0
        self.input_tokens = 0
        self.output_tokens = 0

    def structured(self, models: list[str], system: str, parts: list, schema: type[T], thinking: str = "LOW") -> T:
        cfg = types.GenerateContentConfig(
            system_instruction=system,
            response_mime_type="application/json",
            response_schema=schema,
            thinking_config=types.ThinkingConfig(thinking_level=thinking),
        )
        parts = [types.Part.from_bytes(data=base64.b64decode(p.jpeg_b64), mime_type="image/jpeg")
                 if isinstance(p, Image) else p for p in parts]
        last: Exception | None = None
        for model in models:
            for attempt in range(2):
                try:
                    res = self.client.models.generate_content(model=model, contents=parts, config=cfg)
                    self._count(res)
                    if res.parsed is None:
                        raise ValueError(f"{model} returned no parsable JSON")
                    return res.parsed  # type: ignore[return-value]
                except errors.APIError as e:
                    last = e
                    if e.code in (429, 500, 502, 503, 504) and attempt == 0:
                        time.sleep(0.8)
                        continue
                    break  # other errors, or a second failure: try the next model
        raise RuntimeError(f"Gemini unavailable: {last}")

    def _count(self, res) -> None:
        self.calls += 1
        if u := getattr(res, "usage_metadata", None):
            self.input_tokens += int(u.prompt_token_count or 0)
            self.output_tokens += int(u.candidates_token_count or 0) + int(u.thoughts_token_count or 0)
