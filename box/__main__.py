"""Run the NextStep Box against a phone or simulator.

    python -m box "set an alarm for 7 am" --phone android
    python -m box --phone android --yes "search for weather in Chrome"   # auto-approve (testing)
"""

import argparse
import sys

from .backend import Backend
from .config import Config
from .console import Console
from .runner import Runner


def make_phone(kind: str, serial: str | None):
    if kind == "android":
        from .drivers.android_adb import AndroidAdbDriver
        return AndroidAdbDriver(serial)
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
    a = p.parse_args()

    cfg = Config()
    goal = a.goal or input("🎤 What should I do? > ").strip()
    phone = make_phone(a.phone, a.serial)
    try:
        report = Runner(cfg, Backend(cfg), phone, Console(speak=cfg.speak and not a.quiet, auto_yes=a.yes)).run(goal)
        print(f"\n📊 {report.summary()}")
    finally:
        phone.close()


if __name__ == "__main__":
    main()
