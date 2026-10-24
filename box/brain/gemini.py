"""Gemini, called directly from the box (no server in between = one network hop fewer per step).

The key lives only on the box: env NEXTSTEP_BOX_GEMINI_KEY or ~/.nextstep-box/gemini.key.
Brief overloads (429/5xx) are retried once, then the next model in the list is tried.
"""

import os
import time
from pathlib import Path
from typing import TypeVar

from google import genai
from google.genai import errors, types
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)
KEY_FILE = Path(os.path.expanduser("~/.nextstep-box/gemini.key"))


class NoKey(RuntimeError):
    pass


def load_key() -> str:
    key = os.getenv("NEXTSTEP_BOX_GEMINI_KEY", "").strip()
    if not key and KEY_FILE.exists():
        key = KEY_FILE.read_text().strip()
    if not key:
        raise NoKey(f"No Gemini key. Put it in {KEY_FILE} (chmod 600) or NEXTSTEP_BOX_GEMINI_KEY.")
    return key


class Gemini:
    def __init__(self, key: str | None = None, timeout_s: float = 30.0):
        self.client = genai.Client(api_key=key or load_key(), http_options=types.HttpOptions(timeout=int(timeout_s * 1000)))
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


def image_part(jpeg_b64: str | None) -> list:
    if not jpeg_b64:
        return []
    import base64
    return [types.Part.from_bytes(data=base64.b64decode(jpeg_b64), mime_type="image/jpeg")]
