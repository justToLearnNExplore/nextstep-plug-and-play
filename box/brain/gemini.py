"""Gemini, called directly from the box with a Google AI Studio key (see llm.py for where keys live).

A quick overload (429/5xx) is retried once, then the next model in the list is tried. A model the key
may not use (403/404, e.g. "no longer available to new users") is never tried again; one that is busy
or slow (a 503 after seconds, a 504, a timeout) rests for a few minutes and is tried after the others.
If the last model tried is over its requests-per-minute limit (the free tier allows about 5), the box
waits as long as Google says (at most 30 s) and tries the list once more; a model whose daily limit is
used up (20 requests a day for some free models) is left out until the box restarts.
"""

import base64
import time
from typing import TypeVar

import httpx
from google import genai
from google.genai import errors, types
from pydantic import BaseModel

from .llm import Audio, Image

T = TypeVar("T", bound=BaseModel)
RETRY = {429, 500, 502, 503, 504}
GONE = {403, 404}
REST_S = 300.0
MAX_WAIT_S = 30.0
QUICK_S = 3.0  # only a failure this fast is worth one more try on the same model


def rate_limit_wait(e: errors.APIError) -> float:
    """The wait a 429 asks for (its RetryInfo, e.g. "12s"), else 12 s. More than MAX_WAIT_S means a
    daily limit: not worth waiting for."""
    details = (e.details or {}).get("error", {}).get("details", []) if isinstance(e.details, dict) else []
    for d in details:
        if "RetryInfo" in str(d.get("@type", "")):
            try:
                return max(1.0, float(str(d.get("retryDelay", "12")).rstrip("s")))
            except ValueError:
                break
    return 12.0


class Gemini:
    def __init__(self, key: str, timeout_s: float = 30.0):
        self.client = genai.Client(api_key=key, http_options=types.HttpOptions(timeout=int(timeout_s * 1000)))
        self.calls = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.gone: set[str] = set()
        self.resting: dict[str, float] = {}  # model -> monotonic time until which it is tried last

    def _order(self, models: list[str]) -> list[str]:
        usable = [m for m in models if m not in self.gone]
        now = time.monotonic()
        return [m for m in usable if self.resting.get(m, 0) <= now] + [m for m in usable if self.resting.get(m, 0) > now]

    def structured(self, models: list[str], system: str, parts: list, schema: type[T], thinking: str = "LOW") -> T:
        cfg = types.GenerateContentConfig(
            system_instruction=system,
            response_mime_type="application/json",
            response_schema=schema,
            thinking_config=types.ThinkingConfig(thinking_level=thinking),
        )
        parts = [types.Part.from_bytes(data=base64.b64decode(p.jpeg_b64), mime_type="image/jpeg") if isinstance(p, Image)
                 else types.Part.from_bytes(data=base64.b64decode(p.wav_b64), mime_type="audio/wav") if isinstance(p, Audio)
                 else p for p in parts]
        last: object = None
        for round_ in range(2):
            answer = self._try_models(models, parts, cfg)
            if not isinstance(answer, tuple):
                return answer  # type: ignore[return-value]
            last, wait = answer
            if not wait or round_:
                break
            time.sleep(wait)  # the models are over their per-minute limit: wait once, then try again
        raise RuntimeError(f"Gemini unavailable: {last}")

    def _try_models(self, models: list[str], parts: list, cfg: types.GenerateContentConfig) -> object:
        """The first usable answer, or (last error, seconds to wait if the last refusal was a rate limit)."""
        last: object = None
        wait = 0.0
        for model in self._order(models):
            wait = 0.0
            for attempt in range(2):
                t0 = time.monotonic()
                try:
                    res = self.client.models.generate_content(model=model, contents=parts, config=cfg)
                except errors.APIError as e:
                    last = e
                    wait = rate_limit_wait(e) if e.code == 429 else 0.0
                    if e.code in GONE or wait > MAX_WAIT_S:  # refused, or today's limit is used up
                        self.gone.add(model)
                        wait = 0.0
                    elif e.code in RETRY and attempt == 0 and time.monotonic() - t0 < QUICK_S:
                        time.sleep(0.8)
                        continue
                    elif e.code in RETRY:
                        self.resting[model] = time.monotonic() + REST_S
                    break
                except httpx.TransportError as e:  # timed out, or the network dropped
                    last = e
                    wait = 0.0
                    if attempt == 0 and not isinstance(e, httpx.TimeoutException):
                        time.sleep(0.5)
                        continue
                    self.resting[model] = time.monotonic() + REST_S
                    break
                self._count(res)
                if res.parsed is None:
                    last, wait = f"{model} returned no parsable JSON", 0.0
                    break
                return res.parsed
        return last, wait

    def _count(self, res) -> None:
        self.calls += 1
        if u := getattr(res, "usage_metadata", None):
            self.input_tokens += int(u.prompt_token_count or 0)
            self.output_tokens += int(u.candidates_token_count or 0) + int(u.thoughts_token_count or 0)
