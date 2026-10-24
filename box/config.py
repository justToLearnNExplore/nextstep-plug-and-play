"""Box settings. Defaults point at the live NextStep backend; override with environment variables."""

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Config:
    api_base_url: str = os.getenv("NEXTSTEP_API", "https://nextstep-api-219408489635.asia-south1.run.app")
    # Public Firebase web key (same one the app ships with); empty = local backend without auth.
    firebase_api_key: str = os.getenv("NEXTSTEP_FIREBASE_KEY", "AIzaSyDcuiVVAK-W7SLz6PnA582pdhjTxwjev_M")
    language: str = os.getenv("NEXTSTEP_LANG", "en-IN")
    state_dir: str = field(default_factory=lambda: os.path.expanduser(os.getenv("NEXTSTEP_BOX_STATE", "~/.nextstep-box")))
    max_turns: int = 40
    speak: bool = os.getenv("NEXTSTEP_SPEAK", "1") == "1"
