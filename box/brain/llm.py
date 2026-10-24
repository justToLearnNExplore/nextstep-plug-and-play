"""How the brain reaches a model: Gemini directly, or through Vercel AI Gateway. Both clients offer
the same `structured()` call, so the rest of the box doesn't care which one is in use.

Keys live only on the box, never in the repo:
  ~/.nextstep-box/gemini.key       or NEXTSTEP_BOX_GEMINI_KEY      (Google AI Studio key)
  ~/.nextstep-box/ai-gateway.key   or NEXTSTEP_BOX_AI_GATEWAY_KEY  (Vercel AI Gateway key)
"""

import os
from dataclasses import dataclass
from pathlib import Path

STATE = Path(os.path.expanduser(os.getenv("NEXTSTEP_BOX_STATE", "~/.nextstep-box")))


@dataclass(frozen=True)
class Image:
    jpeg_b64: str


def images(jpeg_b64: str | None) -> list[Image]:
    return [Image(jpeg_b64)] if jpeg_b64 else []


class NoKey(RuntimeError):
    pass


def read_key(env: str, filename: str) -> str:
    key = os.getenv(env, "").strip()
    path = STATE / filename
    if not key and path.exists():
        key = path.read_text().strip()
    return key


def make_llm():
    """Gemini directly when its key is there (one network hop fewer), otherwise Vercel AI Gateway.
    NEXTSTEP_BOX_LLM=gemini|gateway picks one explicitly."""
    choice = os.getenv("NEXTSTEP_BOX_LLM", "").strip().lower()
    gemini_key = read_key("NEXTSTEP_BOX_GEMINI_KEY", "gemini.key")
    gateway_key = read_key("NEXTSTEP_BOX_AI_GATEWAY_KEY", "ai-gateway.key")
    if choice == "gateway" or (choice != "gemini" and gateway_key and not gemini_key):
        if not gateway_key:
            raise NoKey(f"No Vercel AI Gateway key. Put it in {STATE / 'ai-gateway.key'} (chmod 600).")
        from .gateway import Gateway
        return Gateway(gateway_key)
    if not gemini_key:
        raise NoKey(f"No model key. Put a Vercel AI Gateway key in {STATE / 'ai-gateway.key'} or a Gemini key "
                    f"in {STATE / 'gemini.key'} (chmod 600).")
    from .gemini import Gemini
    return Gemini(gemini_key)
