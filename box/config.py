"""Box settings, overridable with environment variables. The box talks to nothing but the phone
and Gemini: no NextStep server, account or database."""

import os
from dataclasses import dataclass, field


def _models(env: str) -> list[str]:
    return [m.strip() for m in os.getenv(env, "").split(",") if m.strip()]


@dataclass(frozen=True)
class Config:
    language: str = os.getenv("NEXTSTEP_LANG", "en-IN")
    state_dir: str = field(default_factory=lambda: os.path.expanduser(os.getenv("NEXTSTEP_BOX_STATE", "~/.nextstep-box")))
    # Comma-separated fallback lists; empty = the brain's defaults.
    planner_models: list[str] = field(default_factory=lambda: _models("NEXTSTEP_BOX_PLANNER_MODELS"))
    operator_models: list[str] = field(default_factory=lambda: _models("NEXTSTEP_BOX_OPERATOR_MODELS"))
    operator_thinking: str = os.getenv("NEXTSTEP_BOX_OPERATOR_THINKING", "LOW")  # MINIMAL / LOW / MEDIUM
    # Added to phone numbers saved without one, for WhatsApp links (91 = India).
    country_code: str = os.getenv("NEXTSTEP_BOX_COUNTRY_CODE", "91")
    max_turns: int = 40
    speak: bool = os.getenv("NEXTSTEP_SPEAK", "1") == "1"
