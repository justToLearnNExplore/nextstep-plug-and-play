"""Run the NextStep Box against a phone or simulator.

    python -m box "set an alarm for 7 am" --phone android
    python -m box --phone android --yes "search for weather in Chrome"   # auto-approve (testing)
    python -m box --phone iphone-mirroring --yes-plan "open the Clock app"  # a real iPhone via iPhone Mirroring
    python -m box --serve --phone android      # plug in and talk: waits for the phone, then listens
    python -m box --hear request.wav           # one spoken request from a recording (testing without a mic)
"""

import argparse
import base64
import subprocess
import sys

from .brain.brain import Brain
from .brain.llm import NoKey, make_llm
from .config import Config
from .console import Console
from .runner import Runner


def make_phone(kind: str, serial: str | None, helper: bool = True):
    if kind == "android":
        from .drivers.android_adb import AndroidAdbDriver
        return AndroidAdbDriver(serial, use_helper=helper)
    if kind == "iphone-mirroring":
        from .drivers.iphone_mirroring import IphoneMirroringDriver
        return IphoneMirroringDriver()
    if kind == "ios-sim":
        from .drivers.ios_sim import IosSimDriver
        return IosSimDriver(serial)
    sys.exit(f"unknown phone kind: {kind}")


def recording(path: str) -> str:
    """Any audio file as the 16 kHz mono WAV the box records, base64."""
    r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", path, "-ac", "1", "-ar", "16000",
                        "-f", "wav", "-"], capture_output=True)
    if r.returncode != 0 or not r.stdout:
        sys.exit(f"could not read {path}: {r.stderr.decode()[-200:]}")
    return base64.b64encode(r.stdout).decode()


def main() -> None:
    p = argparse.ArgumentParser(prog="nextstep-box")
    p.add_argument("goal", nargs="?", help="what the senior would say; asked for if missing")
    p.add_argument("--phone", default="android", choices=["android", "iphone-mirroring", "ios-sim"])
    p.add_argument("--serial", help="adb serial or simulator UDID")
    p.add_argument("--yes", action="store_true", help="approve every question automatically (testing only)")
    p.add_argument("--yes-plan", action="store_true",
                   help="approve the plan, say no to every other question (testing on a real phone)")
    p.add_argument("--quiet", action="store_true", help="don't speak")
    p.add_argument("--no-helper", action="store_true", help="Android: plain ADB only, don't use the helper app")
    p.add_argument("--serve", action="store_true",
                   help="plug in and talk: wait for the phone, say hello, listen, do it, listen again")
    p.add_argument("--hear", metavar="AUDIO", help="one spoken request from a recording instead of typed text")
    a = p.parse_args()

    cfg = Config()
    try:
        llm = make_llm()
    except NoKey as e:
        sys.exit(str(e))
    brain = Brain(llm, cfg.language, cfg.planner_models or None, cfg.operator_models or None, cfg.operator_thinking)
    from .speech import voice_for
    from .voice import Ears, VoiceConsole
    speak, voice = cfg.speak and not a.quiet, voice_for(cfg.language)
    if a.serve:
        from .serve import serve
        ears = Ears()
        ui = VoiceConsole(ears, brain.hear_answer, cfg.language, speak=speak, voice=voice,
                          auto_yes=a.yes, plan_only=a.yes_plan)
        try:
            serve(cfg, brain, a.phone, a.serial, lambda kind, serial: make_phone(kind, serial, helper=not a.no_helper),
                  ui, ears)
        except KeyboardInterrupt:
            print(f"\n   {type(llm).__name__}: {llm.calls} calls, {llm.input_tokens} in / {llm.output_tokens} out tokens")
        return
    speech = recording(a.hear) if a.hear else None
    goal = "" if speech else a.goal or input("🎤 What should I do? > ").strip()
    phone = make_phone(a.phone, a.serial, helper=not a.no_helper)
    try:
        ui = Console(speak=speak, auto_yes=a.yes, plan_only=a.yes_plan, voice=voice)
        report = Runner(cfg, brain, phone, ui).run(goal, speech)
        ui.finish_speaking()
        print(f"\n📊 {report.summary()}")
        print(f"   {type(llm).__name__}: {llm.calls} calls, {llm.input_tokens} in / {llm.output_tokens} out tokens")
    finally:
        phone.close()


if __name__ == "__main__":
    main()
