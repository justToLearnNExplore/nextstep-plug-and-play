"""How the box speaks, on whatever it runs on.

Mac   `say` with an Indian voice: Rishi (English), Lekha (Hindi); macOS has no Kannada voice.
Pi    Piper for English if a voice model is installed (NEXTSTEP_BOX_PIPER_MODEL: more natural), else
      espeak-ng, which runs offline and speaks English, Hindi and Kannada (robotic, but clear).

A voice is a short spec ("say:Rishi", "piper:/path/voice.onnx", "espeak:hi") that the console turns
into a command.
"""

import os
import re
import shutil
import subprocess
import sys

MAC_VOICES = {"en-IN": "Rishi", "hi-IN": "Lekha"}
ESPEAK = {"en-IN": "en", "hi-IN": "hi", "kn-IN": "kn"}


def voice_for(lang: str) -> str | None:
    """The best voice this machine has for `lang`, or None if it can't speak at all."""
    if sys.platform == "darwin" and shutil.which("say"):
        name = MAC_VOICES.get(lang, "")
        listing = subprocess.run(["say", "-v", "?"], capture_output=True, text=True).stdout if name else ""
        return f"say:{name}" if name and re.search(rf"^{name}\s", listing, re.M) else "say:"
    model = os.getenv("NEXTSTEP_BOX_PIPER_MODEL", "")
    if lang == "en-IN" and model and os.path.exists(model) and shutil.which("piper") and shutil.which("aplay"):
        return f"piper:{model}"
    if shutil.which("espeak-ng"):
        return f"espeak:{ESPEAK.get(lang, 'en')}"
    return None


def speech_argv(text: str, voice: str) -> list[str]:
    """The command that says `text` with `voice` (text goes as an argument, never through a shell line)."""
    engine, _, arg = voice.partition(":")
    if engine == "piper":
        return ["sh", "-c", 'printf %s "$1" | piper --model "$2" --output_raw 2>/dev/null | aplay -q -r 22050 -f S16_LE -t raw -',
                "sh", text, arg]
    if engine == "espeak":
        return ["espeak-ng", "-v", arg or "en", "-s", "150", text]
    return ["say", "-r", "185"] + (["-v", arg] if arg else []) + [text]
