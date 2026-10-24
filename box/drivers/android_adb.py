"""Android over ADB: no app on the phone, just USB debugging turned on once.

Eyes: the accessibility tree (`uiautomator dump`) plus an occasional screenshot.
Hands: `input` commands sent through ONE long-lived `adb shell`, so a tap costs a few
milliseconds instead of starting a new adb process each time.
"""

import base64
import hashlib
import io
import queue
import re
import shlex
import subprocess
import threading
import time
import uuid
import xml.etree.ElementTree as ET
from typing import Any

from PIL import Image

from .base import ScreenState, px

ADB = "adb"
DUMP_PATH = "/sdcard/nextstep_ui.xml"

# App names people say -> packages (open_app); anything else is looked up on the phone.
KNOWN_APPS = {
    "blinkit": "com.grofers.customerapp", "uber": "com.ubercab", "whatsapp": "com.whatsapp",
    "youtube": "com.google.android.youtube", "chrome": "com.android.chrome", "clock": "com.google.android.deskclock",
    "camera": "com.android.camera2", "settings": "com.android.settings", "maps": "com.google.android.apps.maps",
    "messages": "com.google.android.apps.messaging", "phone": "com.google.android.dialer",
    "contacts": "com.google.android.contacts", "play store": "com.android.vending", "gmail": "com.google.android.gm",
}
# Links open straight in their app (no "Open with" chooser).
LINK_APPS = {"blinkit.com": "com.grofers.customerapp", "youtube.com": "com.google.android.youtube",
             "m.uber.com": "com.ubercab", "wa.me": "com.whatsapp"}
KEYS = {"enter": 66, "back": 4, "home": 3, "search": 84, "delete": 67, "tab": 61, "volume_up": 24,
        "volume_down": 25, "app_switch": 187}
BOUNDS = re.compile(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]")


class AdbShell:
    """A persistent `adb shell`. Each command's output ends at a unique marker line; a reader
    thread feeds a queue so a stuck command can time out instead of freezing the box."""

    def __init__(self, serial: str | None):
        args = [ADB] + (["-s", serial] if serial else []) + ["shell"]
        self.proc = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                     text=True, bufsize=1)
        self.lines: queue.Queue[str | None] = queue.Queue()
        threading.Thread(target=self._read, daemon=True).start()
        self.lock = threading.Lock()

    def _read(self) -> None:
        assert self.proc.stdout
        for line in self.proc.stdout:
            self.lines.put(line)
        self.lines.put(None)  # shell exited

    def run(self, cmd: str, timeout: float = 20.0) -> str:
        marker = f"__NS_{uuid.uuid4().hex[:8]}__"
        with self.lock:
            assert self.proc.stdin
            # A leading newline keeps the marker on its own line even if the output lacks one.
            self.proc.stdin.write(f"{cmd}; printf '\\n{marker}\\n'\n")
            self.proc.stdin.flush()
            out, deadline = [], time.time() + timeout
            while True:
                try:
                    line = self.lines.get(timeout=max(0.05, deadline - time.time()))
                except queue.Empty:
                    raise TimeoutError(f"adb shell: {cmd[:60]}") from None
                if line is None:
                    raise RuntimeError("adb shell closed")
                if line.strip() == marker:
                    return "".join(out)
                out.append(line)

    def close(self) -> None:
        try:
            self.proc.terminate()
        except OSError:
            pass


class AndroidAdbDriver:
    name = "android"

    def __init__(self, serial: str | None = None):
        self.serial = serial
        self.shell = AdbShell(serial)
        size = self.shell.run("wm size")
        m = re.findall(r"(\d+)x(\d+)", size)
        self.width, self.height = (int(m[-1][0]), int(m[-1][1])) if m else (1080, 1920)

    # ---- eyes ---------------------------------------------------------------------------------

    def capture(self, with_screenshot: bool) -> ScreenState:
        xml = self.shell.run(f"uiautomator dump {DUMP_PATH} >/dev/null 2>&1; cat {DUMP_PATH}")
        package, nodes, secure = parse_ui_xml(xml)
        shot = self._screenshot_b64() if with_screenshot else None
        return ScreenState(package=package, width=self.width, height=self.height, nodes=nodes,
                           screenshot_b64=shot, screenshot_tried=with_screenshot, has_secure_field=secure)

    def _exec_out(self, *args: str) -> bytes:
        cmd = [ADB] + (["-s", self.serial] if self.serial else []) + ["exec-out", *args]
        return subprocess.run(cmd, capture_output=True, timeout=20).stdout

    def _screenshot_b64(self) -> str | None:
        png = self._exec_out("screencap", "-p")
        if not png:
            return None
        img = Image.open(io.BytesIO(png)).convert("RGB")
        img.thumbnail((720, 1600))
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=60)
        return base64.b64encode(buf.getvalue()).decode()

    def _frame_hash(self) -> str:
        # Raw screencap (no PNG encoding) is the cheapest way to notice the screen changing.
        return hashlib.md5(self._exec_out("screencap")).hexdigest()

    def settle(self, max_s: float = 2.5) -> None:
        """Returns as soon as the screen stops changing (two equal frames), at most max_s."""
        time.sleep(0.25)
        deadline, last = time.time() + max_s, self._frame_hash()
        while time.time() < deadline:
            time.sleep(0.2)
            now = self._frame_hash()
            if now == last:
                return
            last = now

    # ---- hands --------------------------------------------------------------------------------

    def execute(self, name: str, args: dict[str, Any], screen: ScreenState) -> dict[str, Any]:
        w, h = self.width, self.height
        sh = self.shell.run
        if name == "click":
            sh(f"input tap {px(args['x'], w)} {px(args['y'], h)}")
        elif name == "long_press":
            x, y = px(args["x"], w), px(args["y"], h)
            sh(f"input swipe {x} {y} {x} {y} {int(float(args.get('seconds', 1.5)) * 1000)}")
        elif name == "drag_and_drop":
            sh(f"input swipe {px(args['start_x'], w)} {px(args['start_y'], h)} "
               f"{px(args['end_x'], w)} {px(args['end_y'], h)} 400")
        elif name == "type":
            text = str(args.get("text", ""))
            if not text.isascii():
                return {"ok": False, "error": "non_ascii_text_needs_ime"}
            sh(f"input text {shlex.quote(text.replace(' ', '%s'))}")
            if args.get("press_enter"):
                sh("input keyevent 66")
        elif name in ("go_back", "go_home"):
            sh(f"input keyevent {4 if name == 'go_back' else 3}")
        elif name == "press_key":
            sh(f"input keyevent {KEYS.get(str(args.get('key', 'enter')).lower(), 66)}")
        elif name == "open_app":
            pkg = self._package_for(str(args.get("app_name", "")))
            if not pkg:
                return {"ok": False, "error": "not_installed", "app_name": args.get("app_name")}
            sh(f"monkey -p {pkg} -c android.intent.category.LAUNCHER 1 >/dev/null 2>&1")
        elif name == "open_link":
            url = str(args["url"])
            pkg = next((p for host, p in LINK_APPS.items() if host in url and self._installed(p)), None)
            sh(f"am start -a android.intent.action.VIEW -d {shlex.quote(url)}" + (f" -p {pkg}" if pkg else "") + " >/dev/null")
        elif name == "open_play_store":
            sh(f"am start -a android.intent.action.VIEW -d market://details?id={shlex.quote(str(args['package']))} >/dev/null")
        elif name == "wait_for_app":
            deadline = time.time() + float(args.get("timeout_s", 180))
            while time.time() < deadline and not self._installed(str(args["package"])):
                time.sleep(2)
            if not self._installed(str(args["package"])):
                return {"ok": False, "error": "install_timeout"}
            sh(f"monkey -p {args['package']} -c android.intent.category.LAUNCHER 1 >/dev/null 2>&1")
        elif name == "wait":
            self.settle(min(float(args.get("seconds", 1)), 5.0))
            return {"ok": True}
        elif name == "take_screenshot":
            return {"ok": True}
        else:
            return {"ok": False, "error": f"unsupported_action:{name}"}
        self.settle()
        return {"ok": True}

    def _installed(self, pkg: str) -> bool:
        return "package:" in self.shell.run(f"pm path {pkg} 2>/dev/null")

    def _package_for(self, app_name: str) -> str | None:
        key = app_name.strip().lower()
        if key in KNOWN_APPS and self._installed(KNOWN_APPS[key]):
            return KNOWN_APPS[key]
        if "." in key and self._installed(key):
            return key  # already a package name
        listing = self.shell.run("pm list packages")
        word = re.sub(r"[^a-z0-9]", "", key)
        hits = [l.removeprefix("package:").strip() for l in listing.splitlines() if word and word in l.lower()]
        return min(hits, key=len) if hits else None

    def close(self) -> None:
        self.shell.close()


def parse_ui_xml(xml: str) -> tuple[str, list[dict[str, Any]], bool]:
    """uiautomator XML -> (foreground package, visible meaningful nodes, has a password field)."""
    start = xml.find("<?xml")
    if start < 0:
        return "", [], False
    root = ET.fromstring(xml[start:])
    nodes: list[dict[str, Any]] = []
    package, secure = "", False
    for el in root.iter("node"):
        a = el.attrib
        package = package or a.get("package", "")
        m = BOUNDS.match(a.get("bounds", ""))
        if not m:
            continue
        b = [int(v) for v in m.groups()]
        if b[2] <= b[0] or b[3] <= b[1]:
            continue  # off-screen / zero-size
        text, desc = a.get("text", ""), a.get("content-desc", "")
        is_pw = a.get("password") == "true"
        click = a.get("clickable") == "true" or a.get("long-clickable") == "true"
        edit = "EditText" in a.get("class", "")
        if not (text or desc or click or edit):
            continue
        n: dict[str, Any] = {"i": len(nodes), "cls": a.get("class", "").rsplit(".", 1)[-1], "b": b}
        if is_pw:
            n["secure"] = True
            secure = True
        elif text:
            n["text"] = text[:200]
        if desc:
            n["desc"] = desc[:200]
        if rid := a.get("resource-id"):
            n["id"] = rid.split(":id/")[-1]
        if click:
            n["click"] = True
        if edit:
            n["edit"] = True
        if a.get("scrollable") == "true":
            n["scroll"] = True
        if a.get("focused") == "true":
            n["focus"] = True
        nodes.append(n)
    return package, nodes, secure
