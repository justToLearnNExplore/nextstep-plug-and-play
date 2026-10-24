"""Common interruptions closed by rule, without asking the AI (rebuilt from NextStep's rules).

Only dismissive, harmless choices are made here ("Not now", "Skip", "Close"). Anything that grants,
buys, sends or signs in is left to the AI and the safety gates.
"""

import re
from typing import Any

from ..drivers.base import ScreenState

DISMISS = re.compile(r"^(not now|no thanks|no, thanks|skip|maybe later|later|remind me later|close|dismiss|cancel|"
                     r"अभी नहीं|बाद में|छोड़ें|ಈಗ ಬೇಡ|ನಂತರ|ಬಿಟ್ಟುಬಿಡಿ)$", re.I)
# Words that show the dialog is an interruption, not part of the task.
INTERRUPTION = re.compile(r"(rate (us|this app)|enjoying|update available|new version|turn on notifications|"
                          r"allow notifications|subscribe to|sign up for offers|install our app|special offer|"
                          r"advertisement|what'?s new)", re.I)


def label(n: dict[str, Any]) -> str:
    return str(n.get("text") or n.get("desc") or "").strip()


def dismiss_button(screen: ScreenState) -> dict[str, Any] | None:
    """The 'Not now' / 'Close' button of a known interruption on this screen, or None."""
    if not any(INTERRUPTION.search(label(n)) for n in screen.nodes if not n.get("secure")):
        return None
    return next((n for n in screen.nodes if n.get("click") and DISMISS.match(label(n))), None)
