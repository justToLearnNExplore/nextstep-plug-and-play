"""Stand-in for the box's face while there is no hardware: the terminal is the screen, Enter is
the big button, and macOS `say` is the speaker. On the real box this becomes the LED ring,
button and speaker; the agent loop doesn't change."""

import shutil
import subprocess
import sys


class Console:
    def __init__(self, speak: bool = True, auto_yes: bool = False):
        self.speak_enabled = speak and shutil.which("say") is not None
        self.auto_yes = auto_yes
        self._voice: subprocess.Popen | None = None

    def _speak(self, text: str) -> None:
        if not self.speak_enabled or not text:
            return
        if self._voice and self._voice.poll() is None:
            self._voice.terminate()  # newest message wins, like the app
        self._voice = subprocess.Popen(["say", "-r", "185", text])

    def status(self, text: str, speak: bool = False) -> None:
        print(f"  · {text}", flush=True)
        if speak:
            self._speak(text)

    def say(self, text: str) -> None:
        print(f"\n🔈 {text}\n", flush=True)
        self._speak(text)

    def timing(self, t) -> None:
        shot = " +screenshot" if t.screenshot else ""
        print(f"    ⏱ see {t.capture_ms} ms · think {t.think_ms} ms{shot} · act {t.act_ms} ms "
              f"[{t.actions} action(s), {t.checked} checked on the box]", flush=True)

    def ask(self, question: str, details: list[str] | None = None, yes: str = "Yes", no: str = "No") -> bool:
        print(f"\n❓ {question}")
        for d in details or []:
            print(f"     ✓ {d}")
        self._speak(question)
        if self.auto_yes:
            print(f"   [{yes}] (auto)")
            return True
        if not sys.stdin.isatty():
            return False
        answer = input(f"   Enter = {yes} · n = {no} > ").strip().lower()
        return answer in ("", "y", "yes")
