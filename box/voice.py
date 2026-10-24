"""The box's ears and voice, on a Mac for now (the real box: a small microphone and speaker).

Ears   the Mac's own microphone through ffmpeg, 16 kHz mono. Listening starts when someone speaks and
       stops after a second of quiet. That is decided on the box from loudness alone, so nothing is
       sent anywhere while it is quiet; what was said is understood by the brain (Gemini hears the
       recording itself, in English, Hindi or Kannada).
Voice  macOS `say` with an Indian voice for the box's language: Rishi (English), Lekha (Hindi).
       macOS has no Kannada voice yet.
"""

import array
import base64
import io
import math
import os
import re
import subprocess
import time
import wave

from .console import Console
from .phrases import phrase

RATE = 16000
FRAME_S = 0.02
FRAME_BYTES = int(RATE * FRAME_S) * 2  # 16-bit samples
VOICES = {"en-IN": "Rishi", "hi-IN": "Lekha"}


def voice_for(lang: str) -> str | None:
    """The macOS voice for `lang`, if it is installed."""
    name = VOICES.get(lang)
    if not name:
        return None
    listing = subprocess.run(["say", "-v", "?"], capture_output=True, text=True).stdout
    return name if re.search(rf"^{name}\s", listing, re.M) else None


def wav_bytes(pcm: bytes) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm)
    return buf.getvalue()


def loudness(frame: bytes) -> float:
    samples = array.array("h", frame[: len(frame) // 2 * 2])
    return math.sqrt(sum(s * s for s in samples) / max(len(samples), 1))


def find_microphone() -> str:
    """ffmpeg's index of the Mac's own microphone (not an iPhone's, which macOS also offers).
    NEXTSTEP_BOX_MIC picks another one by index or by part of its name."""
    listing = subprocess.run(["ffmpeg", "-hide_banner", "-f", "avfoundation", "-list_devices", "true", "-i", ""],
                             capture_output=True, text=True).stderr
    devices = re.findall(r"\[(\d+)\] (.+)", listing.split("audio devices:", 1)[-1])
    want = os.getenv("NEXTSTEP_BOX_MIC", "").strip().lower()
    for index, name in devices:
        if want and (want == index or want in name.lower()):
            return index
    for index, name in devices:
        if not want and "iphone" not in name.lower():
            return index
    if devices:
        return devices[0][0]
    raise RuntimeError("No microphone found (and allow Microphone access for the app that runs the box).")


class Ears:
    """Records one thing said: from when someone starts speaking until a second of quiet."""

    def __init__(self, device: str | None = None):
        self.device = device or find_microphone()

    def listen(self, wait_s: float = 8.0, max_s: float = 15.0, quiet_s: float = 1.0) -> bytes | None:
        """A WAV of what was said, or None if nobody spoke within wait_s."""
        proc = subprocess.Popen(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "avfoundation",
                                 "-i", f":{self.device}", "-ac", "1", "-ar", str(RATE), "-f", "s16le", "-"],
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        try:
            return self._utterance(proc.stdout, wait_s, max_s, quiet_s)  # type: ignore[arg-type]
        finally:
            proc.terminate()
            proc.wait()

    @staticmethod
    def _utterance(stream, wait_s: float, max_s: float, quiet_s: float) -> bytes | None:
        frames = lambda s: int(s / FRAME_S)  # noqa: E731
        first = [stream.read(FRAME_BYTES) for _ in range(frames(0.3))]  # the room's own noise
        threshold = max(400.0, 3 * sum(loudness(f) for f in first) / max(len(first), 1))
        before, speech, loud, quiet = list(first[-frames(0.3):]), [], 0, 0
        deadline = time.monotonic() + wait_s
        while True:
            frame = stream.read(FRAME_BYTES)
            if len(frame) < FRAME_BYTES:
                return None  # the microphone stopped
            level = loudness(frame)
            if not speech:
                before = (before + [frame])[-frames(0.3):]  # keep the start of the first word
                loud = loud + 1 if level > threshold else 0
                if loud >= 3:
                    speech = before[:]
                elif time.monotonic() > deadline:
                    return None
                continue
            speech.append(frame)
            quiet = quiet + 1 if level < threshold * 0.6 else 0
            if quiet >= frames(quiet_s) or len(speech) >= frames(max_s):
                return wav_bytes(b"".join(speech))


def recording_b64(wav: bytes) -> str:
    return base64.b64encode(wav).decode()


class VoiceConsole(Console):
    """The box's face when it listens: its questions are answered aloud ("yes", "haan", "done", "no")."""

    def __init__(self, ears: Ears, understand, lang: str, speak: bool = True, voice: str | None = None,
                 auto_yes: bool = False, plan_only: bool = False):
        super().__init__(speak=speak, auto_yes=auto_yes, plan_only=plan_only, voice=voice)
        self.ears, self.understand, self.lang = ears, understand, lang  # understand(wav_b64, question) -> str

    def ask(self, question: str, details: list[str] | None = None, yes: str = "Yes", no: str = "No",
            plan: bool = False) -> bool:
        if self.auto_yes or self.plan_only:  # testing: answered without listening
            return super().ask(question, details, yes, no, plan)
        print(f"\n❓ {question}")
        for d in details or []:
            print(f"     ✓ {d}")
        for attempt in range(2):
            self.speak_now(question if attempt == 0 else phrase(self.lang, "say_yes_no"))
            wav = self.ears.listen(wait_s=8.0, max_s=6.0)
            if wav is None:
                continue
            answer = self.understand(recording_b64(wav), question)
            print(f"   🎤 {answer}", flush=True)
            if answer in ("yes", "no"):
                return answer == "yes"
        print(f"   [{no}] (no clear answer)")
        return False

