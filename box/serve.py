"""Plug in and talk: the box waits for a phone, says hello, listens, does what it hears, and listens again.

This is the box's whole life on the real hardware: it gets power, a phone is plugged in, and the
person just speaks. On a Mac: `python -m box --serve --phone android` (or iphone-mirroring).
Unplugging the phone ends the session; plugging one in again starts a new one.
"""

import subprocess
import time
from typing import Callable

from .brain.brain import Brain
from .config import Config
from .phrases import phrase
from .runner import Runner
from .voice import Ears, VoiceConsole, recording_b64


def phone_state(kind: str, serial: str | None) -> str:
    """'ready', 'unauthorized' (Android: Allow for USB debugging not tapped yet) or 'absent'."""
    if kind == "android":
        try:
            r = subprocess.run(["adb"] + (["-s", serial] if serial else []) + ["get-state"],
                               capture_output=True, text=True, timeout=10)
        except (OSError, subprocess.TimeoutExpired):
            return "absent"
        out = (r.stdout + r.stderr).strip()
        return "ready" if out == "device" else "unauthorized" if "unauthorized" in out else "absent"
    if kind == "iphone-mirroring":  # "plugged in" = iPhone Mirroring shows the iPhone
        from .drivers.iphone_mirroring import MirrorHelper
        helper = MirrorHelper()
        try:
            return "ready" if helper.call("window").get("ok") else "absent"
        finally:
            helper.close()
    return "ready"


def serve(cfg: Config, brain: Brain, kind: str, serial: str | None, make_phone: Callable, ui: VoiceConsole,
          ears: Ears, state: Callable[[str, str | None], str] = phone_state, sleep: Callable = time.sleep) -> None:
    """Runs until stopped (Ctrl+C)."""
    lang, told = cfg.language, ""
    while True:
        now = state(kind, serial)
        if now != "ready":
            if now != told:
                if now == "unauthorized":
                    ui.say(phrase(lang, "allow_debugging"))
                else:
                    ui.status("Waiting for a phone to be plugged in…")
            told = now
            sleep(1.0)
            continue
        told = ""
        phone = make_phone(kind, serial)
        try:
            ui.speak_now(phrase(lang, "greeting"))
            while state(kind, serial) == "ready":
                ui.status("🎤 listening…")
                ui.face.listening()
                wav = ears.listen(wait_s=10.0, pressed=ui.face.pressed)
                if wav == b"":  # the button: "listen now"
                    ui.speak_now(phrase(lang, "yes_tell_me"))
                    wav = ears.listen(wait_s=10.0)
                if not wav:
                    continue  # nobody spoke: look at the phone and listen again
                ui.face.thinking()
                report = Runner(cfg, brain, phone, ui).run(speech_wav_b64=recording_b64(wav))
                ui.status(f"📊 {report.summary()}")
                ui.finish_speaking()
        except (RuntimeError, OSError, TimeoutError) as e:  # usually: the phone went away in the middle
            ui.status(f"({str(e)[:200]})")
        finally:
            phone.close()
            ui.face.idle()
        ui.speak_now(phrase(lang, "unplugged"))
