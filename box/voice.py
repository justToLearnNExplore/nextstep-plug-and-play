"""The box's ears, and the console that asks its questions aloud (its voice is speech.py).

Ears   the microphone, 16 kHz mono: the Mac's own through ffmpeg, or the Pi's I2S microphone through
       arecord. Listening starts when someone speaks and stops after a second of quiet. That is decided
       on the box from loudness alone, so nothing is sent anywhere while it is quiet; what was said is
       understood by the brain (Gemini hears the recording itself, in English, Hindi or Kannada).
       On the Pi a press of the button also counts: "listen now", or "yes" / "done" to a question.
"""

import array
import base64
import io
import math
import os
import re
import subprocess
import sys
import time
import wave
from typing import Callable

from .console import Console
from .face import Face
from .phrases import phrase

RATE = 16000
FRAME_S = 0.02
FRAME_BYTES = int(RATE * FRAME_S) * 2  # 16-bit samples
MIN_LEVEL = float(os.getenv("NEXTSTEP_BOX_MIC_MIN", "400"))  # quietest speech counted (raise in a noisy room)


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
    """The microphone: on a Mac ffmpeg's index of its own (not an iPhone's, which macOS also offers), on
    Linux the first ALSA capture card. NEXTSTEP_BOX_MIC picks another (index, part of a name, ALSA device)."""
    if sys.platform != "darwin":
        if os.getenv("NEXTSTEP_BOX_MIC"):
            return os.environ["NEXTSTEP_BOX_MIC"]
        cards = re.findall(r"^card (\d+):.*device (\d+):", subprocess.run(["arecord", "-l"], capture_output=True,
                                                                         text=True).stdout, re.M)
        return f"plughw:{cards[0][0]},{cards[0][1]}" if cards else "default"
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

    def command(self) -> list[str]:
        if sys.platform == "darwin":
            return ["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "avfoundation", "-i", f":{self.device}",
                    "-ac", "1", "-ar", str(RATE), "-f", "s16le", "-"]
        return ["arecord", "-q", "-D", self.device, "-f", "S16_LE", "-r", str(RATE), "-c", "1", "-t", "raw"]

    def listen(self, wait_s: float = 8.0, max_s: float = 15.0, quiet_s: float = 1.0,
               pressed: Callable[[], bool] | None = None) -> bytes | None:
        """A WAV of what was said; None if nobody spoke within wait_s; b"" if the button was pressed."""
        proc = subprocess.Popen(self.command(), stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        try:
            return self._utterance(proc.stdout, wait_s, max_s, quiet_s, pressed)  # type: ignore[arg-type]
        finally:
            proc.terminate()
            proc.wait()

    @staticmethod
    def _utterance(stream, wait_s: float, max_s: float, quiet_s: float,
                   pressed: Callable[[], bool] | None = None) -> bytes | None:
        frames = lambda s: int(s / FRAME_S)  # noqa: E731
        first = [stream.read(FRAME_BYTES) for _ in range(frames(0.3))]  # the room's own noise
        threshold = max(MIN_LEVEL, 3 * sum(loudness(f) for f in first) / max(len(first), 1))
        before, speech, loud, quiet = list(first[-frames(0.3):]), [], 0, 0
        deadline = time.monotonic() + wait_s
        while True:
            frame = stream.read(FRAME_BYTES)
            if len(frame) < FRAME_BYTES:
                return None  # the microphone stopped
            level = loudness(frame)
            if not speech and pressed is not None and pressed():
                return b""  # the button: "listen now", or "yes"
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
                 auto_yes: bool = False, plan_only: bool = False, face: Face | None = None):
        super().__init__(speak=speak, auto_yes=auto_yes, plan_only=plan_only, voice=voice)
        self.ears, self.understand, self.lang = ears, understand, lang  # understand(wav_b64, question) -> str
        self.face = face or Face()

    def ask(self, question: str, details: list[str] | None = None, yes: str = "Yes", no: str = "No",
            plan: bool = False) -> bool:
        if self.auto_yes or self.plan_only:  # testing: answered without listening
            return super().ask(question, details, yes, no, plan)
        print(f"\n❓ {question}")
        for d in details or []:
            print(f"     ✓ {d}")
        for attempt in range(2):
            self.speak_now(question if attempt == 0 else phrase(self.lang, "say_yes_no"))
            self.face.asking()
            wav = self.ears.listen(wait_s=8.0, max_s=6.0, pressed=self.face.pressed)
            self.face.thinking()
            if wav == b"":
                print(f"   [{yes}] (button)", flush=True)
                return True
            if wav is None:
                continue
            answer = self.understand(recording_b64(wav), question)
            print(f"   🎤 {answer}", flush=True)
            if answer in ("yes", "no"):
                return answer == "yes"
        print(f"   [{no}] (no clear answer)")
        return False

