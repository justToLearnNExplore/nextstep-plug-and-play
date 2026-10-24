"""Stand-in for the box's face while there is no hardware: the terminal is the screen, Enter is
the big button, and the computer's speech (speech.py) is the speaker. On the real box the button and
light are face.py; the agent loop doesn't change."""

import subprocess
import sys

from .speech import speech_argv


class Console:
    def __init__(self, speak: bool = True, auto_yes: bool = False, plan_only: bool = False, voice: str | None = None):
        self.speak_enabled = speak and voice is not None
        self.voice = voice  # speech.voice_for(): "say:Rishi", "espeak:hi"...; None = this machine can't speak
        self.auto_yes = auto_yes
        self.plan_only = plan_only  # testing on a real phone: yes to the plan, no to everything else
        self._speaking: subprocess.Popen | None = None

    def _say(self, text: str) -> list[str]:
        return speech_argv(text, self.voice or "")

    def _speak(self, text: str) -> None:
        if not self.speak_enabled or not text:
            return
        if self._speaking and self._speaking.poll() is None:
            self._speaking.terminate()  # newest message wins, like the app
        self._speaking = subprocess.Popen(self._say(text))

    def finish_speaking(self) -> None:
        """Waits until the box has stopped talking (before it listens, so it doesn't hear itself)."""
        if self._speaking and self._speaking.poll() is None:
            self._speaking.wait()

    def speak_now(self, text: str) -> None:
        """Says `text` after whatever is being said, and returns when done."""
        print(f"\n🔈 {text}\n", flush=True)
        self.finish_speaking()
        if self.speak_enabled and text:
            subprocess.run(self._say(text))

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

    def ask(self, question: str, details: list[str] | None = None, yes: str = "Yes", no: str = "No",
            plan: bool = False) -> bool:
        print(f"\n❓ {question}")
        for d in details or []:
            print(f"     ✓ {d}")
        self._speak(question)
        if self.auto_yes:
            print(f"   [{yes}] (auto)")
            return True
        if self.plan_only:
            print(f"   [{yes if plan else no}] (auto)")
            return plan
        if not sys.stdin.isatty():
            return False
        answer = input(f"   Enter = {yes} · n = {no} > ").strip().lower()
        return answer in ("", "y", "yes")
