"""Run the NextStep Box against a phone or simulator.

    python -m box "set an alarm for 7 am" --phone android
    python -m box --phone android --yes "search for weather in Chrome"   # auto-approve (testing)
"""

import argparse
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
    if kind == "ios-sim":
        from .drivers.ios_sim import IosSimDriver
        return IosSimDriver(serial)
    sys.exit(f"unknown phone kind: {kind}")


def main() -> None:
    p = argparse.ArgumentParser(prog="nextstep-box")
    p.add_argument("goal", nargs="?", help="what the senior would say; asked for if missing")
    p.add_argument("--phone", default="android", choices=["android", "ios-sim"])
    p.add_argument("--serial", help="adb serial or simulator UDID")
    p.add_argument("--yes", action="store_true", help="approve every question automatically (testing only)")
    p.add_argument("--quiet", action="store_true", help="don't speak")
    p.add_argument("--no-helper", action="store_true", help="Android: plain ADB only, don't use the helper app")
    a = p.parse_args()

    cfg = Config()
    try:
        llm = make_llm()
    except NoKey as e:
        sys.exit(str(e))
    brain = Brain(llm, cfg.language, cfg.planner_models or None, cfg.operator_models or None)
    goal = a.goal or input("🎤 What should I do? > ").strip()
    phone = make_phone(a.phone, a.serial, helper=not a.no_helper)
    try:
        report = Runner(cfg, brain, phone, Console(speak=cfg.speak and not a.quiet, auto_yes=a.yes)).run(goal)
        print(f"\n📊 {report.summary()}")
        print(f"   {type(llm).__name__}: {llm.calls} calls, {llm.input_tokens} in / {llm.output_tokens} out tokens")
    finally:
        phone.close()


if __name__ == "__main__":
    main()
