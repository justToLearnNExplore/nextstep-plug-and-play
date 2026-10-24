"""iPhone stand-in: Xcode's iOS Simulator driven by Meta's `idb` (needs Xcode + idb installed).

It exercises the whole agent loop on iOS screens (Settings, Safari, Maps, Reminders...) before any
hardware exists. Eyes: `idb ui describe-all` (the accessibility tree) and `idb screenshot`.
Hands: `idb ui tap/swipe/text/key`. The real-iPhone driver (USB/Bluetooth HID + AirPlay) will
keep this interface; only how taps are delivered changes.

Status: written ahead of Xcode being installed, NOT yet run against a simulator.
"""

import base64
import io
import json
import re
import shutil
import subprocess
from typing import Any

from PIL import Image

from .base import ScreenState, px

IDB = shutil.which("idb") or "idb"
HID_ENTER = 40
FRAME = re.compile(r"[-\d.]+")


class IosSimDriver:
    name = "ios-sim"

    def __init__(self, udid: str | None = None):
        self.udid = udid or self._booted_udid()
        info = json.loads(self._idb("describe", "--json"))
        dims = info.get("screen_dimensions", {})
        density = float(dims.get("density", 3.0)) or 3.0
        # idb taps and accessibility frames are in points; the backend wants a pixel-like space.
        self.width = int(dims.get("width", 1179) / density)
        self.height = int(dims.get("height", 2556) / density)

    def _idb(self, *args: str, timeout: float = 20.0) -> str:
        cmd = [IDB, *args, "--udid", self.udid]
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=True).stdout

    @staticmethod
    def _booted_udid() -> str:
        out = subprocess.run(["xcrun", "simctl", "list", "devices", "booted", "--json"], capture_output=True,
                             text=True, check=True).stdout
        for devices in json.loads(out)["devices"].values():
            for d in devices:
                if d.get("state") == "Booted":
                    return d["udid"]
        raise RuntimeError("No booted iOS Simulator. Boot one in Xcode or with `xcrun simctl boot`.")

    def capture(self, with_screenshot: bool) -> ScreenState:
        elements = json.loads(self._idb("ui", "describe-all", "--json"))
        nodes: list[dict[str, Any]] = []
        secure = False
        for el in elements:
            f = el.get("frame") or {}
            if f:
                x, y, w, h = f.get("x", 0), f.get("y", 0), f.get("width", 0), f.get("height", 0)
            else:
                nums = [float(v) for v in FRAME.findall(str(el.get("AXFrame", "")))]
                if len(nums) < 4:
                    continue
                x, y, w, h = nums[:4]
            if w <= 0 or h <= 0:
                continue
            label, value, role = el.get("AXLabel") or "", el.get("AXValue") or "", el.get("role_description") or el.get("type") or ""
            is_secure = "secure" in role.lower()
            interactive = role.lower() in ("button", "link", "text field", "search field", "cell", "switch", "tab")
            if not (label or value or interactive):
                continue
            n: dict[str, Any] = {"i": len(nodes), "cls": role, "b": [int(x), int(y), int(x + w), int(y + h)]}
            if is_secure:
                n["secure"], secure = True, True
            elif label or value:
                n["text"] = (label or value)[:200]
            if interactive:
                n["click"] = True
            if "field" in role.lower():
                n["edit"] = True
            nodes.append(n)
        return ScreenState(package="ios", width=self.width, height=self.height, nodes=nodes,
                           screenshot_b64=self._screenshot_b64() if with_screenshot else None,
                           screenshot_tried=with_screenshot, has_secure_field=secure)

    def _screenshot_b64(self) -> str | None:
        raw = subprocess.run([IDB, "screenshot", "--udid", self.udid, "-"], capture_output=True, timeout=20).stdout
        if not raw:
            return None
        img = Image.open(io.BytesIO(raw)).convert("RGB")
        img.thumbnail((720, 1600))
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=60)
        return base64.b64encode(buf.getvalue()).decode()

    def execute(self, name: str, args: dict[str, Any], screen: ScreenState) -> dict[str, Any]:
        w, h = self.width, self.height
        if name == "click":
            self._idb("ui", "tap", str(px(args["x"], w)), str(px(args["y"], h)))
        elif name == "long_press":
            self._idb("ui", "tap", str(px(args["x"], w)), str(px(args["y"], h)), "--duration", str(args.get("seconds", 1.5)))
        elif name == "drag_and_drop":
            self._idb("ui", "swipe", *(str(px(args[k], w if k.endswith("x") else h))
                                       for k in ("start_x", "start_y", "end_x", "end_y")))
        elif name == "type":
            self._idb("ui", "text", str(args.get("text", "")))
            if args.get("press_enter"):
                self._idb("ui", "key", str(HID_ENTER))
        elif name in ("go_home",):
            self._idb("ui", "button", "HOME")
        elif name == "open_link":
            self._idb("open", str(args["url"]))
        elif name == "open_app":
            bundle = self._bundle_for(str(args.get("app_name", "")))
            if not bundle:
                return {"ok": False, "error": "not_installed", "app_name": args.get("app_name")}
            self._idb("launch", bundle)
        elif name in ("wait", "take_screenshot"):
            return {"ok": True}
        else:
            return {"ok": False, "error": f"unsupported_action:{name}"}
        return {"ok": True}

    def _bundle_for(self, app_name: str) -> str | None:
        apps = [json.loads(line) for line in self._idb("list-apps", "--json").splitlines() if line.strip()]
        key = app_name.strip().lower()
        for a in apps:
            if key in (a.get("name", "").lower(), a.get("bundle_id", "").lower()):
                return a["bundle_id"]
        hits = [a["bundle_id"] for a in apps if key and key in a.get("name", "").lower()]
        return hits[0] if hits else None

    def close(self) -> None:
        pass
