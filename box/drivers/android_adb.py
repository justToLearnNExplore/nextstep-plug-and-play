"""Android over ADB: the user turns on USB debugging once; the box does the rest.

Fast path: the box installs its small helper app (helper/, see android_helper.py) and talks to it
while plugged in: screen reads in ~20 ms, taps in ~10 ms, typing in any language, one-step alarms.
Plain-ADB path (used automatically if the helper can't run): the accessibility tree from
`uiautomator dump` (~1.1 s) and `input` commands through ONE long-lived `adb shell`.
"""

import base64
import io
import os
import queue
import re
import shlex
import subprocess
import threading
import time
import uuid
import xml.etree.ElementTree as ET
from typing import Any
from urllib.parse import quote

from PIL import Image

from .android_helper import Helper
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
             "m.uber.com": "com.ubercab", "wa.me": "com.whatsapp", "google.com/maps": "com.google.android.apps.maps"}
KEYS = {"enter": 66, "back": 4, "home": 3, "search": 84, "delete": 67, "tab": 61, "volume_up": 24,
        "volume_down": 25, "app_switch": 187}
BOUNDS = re.compile(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]")
CONTACT_ROW = re.compile(r"^Row: \d+ display_name=(.*), data1=(.*)$", re.M)
SMS_ROW = re.compile(r"^Row: \d+ address=(.*?), body=(.*), date=(\d+)$", re.M)
# "What did I miss?" reads these apps' notifications (SMS itself comes from the inbox).
MESSAGE_APPS = {"com.whatsapp": "WhatsApp", "com.whatsapp.w4b": "WhatsApp", "com.truecaller": "Truecaller",
                "org.telegram.messenger": "Telegram", "com.google.android.gm": "Gmail"}
OFFHOOK = 2  # TelephonyManager.CALL_STATE_OFFHOOK: a call is being dialled or is going on


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

    def __init__(self, serial: str | None = None, use_helper: bool = os.getenv("NEXTSTEP_BOX_NO_HELPER") != "1"):
        self.serial = serial
        self.shell = AdbShell(serial)
        size = self.shell.run("wm size")
        m = re.findall(r"(\d+)x(\d+)", size)
        self.width, self.height = (int(m[-1][0]), int(m[-1][1])) if m else (1080, 1920)
        self.helper = Helper.start([ADB] + (["-s", serial] if serial else []), self.shell) if use_helper else None

    def _h(self, cmd: str, **args: Any) -> dict[str, Any] | None:
        """A helper call, or None when there is no helper (the caller then uses plain ADB)."""
        if not self.helper:
            return None
        try:
            return self.helper.call(cmd, **args)
        except (OSError, ValueError) as e:
            print(f"  (helper stopped: {e}; using plain ADB)", flush=True)
            self.helper.close()
            self.helper = None
            return None

    def _try(self, cmd: str, **args: Any) -> bool:
        r = self._h(cmd, **args)
        return bool(r and r.get("ok"))

    # ---- eyes ---------------------------------------------------------------------------------

    def capture(self, with_screenshot: bool) -> ScreenState:
        d = self._h("dump")
        if d and d.get("ok"):
            self.width, self.height = d["w"], d["h"]  # follows rotation
            package, nodes, secure = d["package"], d["nodes"], d["secure"]
        else:
            # Old dump removed first: on a moving screen (a running timer) the dump fails, and the box
            # must then see nothing (and take a screenshot), not the previous screen.
            xml = self.shell.run(f"rm -f {DUMP_PATH}; uiautomator dump {DUMP_PATH} >/dev/null 2>&1; cat {DUMP_PATH} 2>/dev/null")
            package, nodes, secure = parse_ui_xml(xml)
        shot = self._screenshot_b64() if with_screenshot else None
        return ScreenState(package=package, width=self.width, height=self.height, nodes=nodes,
                           screenshot_b64=shot, screenshot_tried=with_screenshot, has_secure_field=secure)

    def _exec_out(self, *args: str) -> bytes:
        cmd = [ADB] + (["-s", self.serial] if self.serial else []) + ["exec-out", *args]
        return subprocess.run(cmd, capture_output=True, timeout=20).stdout

    def _screenshot_b64(self) -> str | None:
        r = self._h("screenshot", max_w=720, quality=60)
        if r and r.get("ok"):
            return r["jpeg_b64"]
        png = self._exec_out("screencap", "-p")
        if not png:
            return None
        img = Image.open(io.BytesIO(png)).convert("RGB")
        img.thumbnail((720, 1600))
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=60)
        return base64.b64encode(buf.getvalue()).decode()

    def _frame_hash(self) -> str:
        # Hashed on the phone: ~50 ms, versus ~350 ms to pull the raw 8 MB frame over USB.
        return self.shell.run("screencap | md5sum").split(" ", 1)[0].strip()

    def settle(self, max_s: float = 2.5) -> None:
        """Returns as soon as the screen stops changing (two equal frames), at most max_s."""
        if self._try("settle", max_ms=int(max_s * 1000)):
            return
        time.sleep(0.15)
        deadline, last = time.time() + max_s, self._frame_hash()
        while time.time() < deadline:
            time.sleep(0.12)
            now = self._frame_hash()
            if now == last:
                return
            last = now

    def wake(self) -> dict[str, Any]:
        """Screen on and past a lock screen without a PIN; locked=True means the user must unlock it.
        A sleeping phone ignores every tap, and phones are usually asleep when someone asks for help."""
        if "mWakefulness=Awake" not in self.shell.run("dumpsys power | grep mWakefulness="):
            self.shell.run("input keyevent 224")  # KEYCODE_WAKEUP: turns the screen on, never off
            self.settle()
        if "mIsShowing=true" in self.shell.run("dumpsys window | grep mIsShowing="):
            self.shell.run("wm dismiss-keyguard")
            self.settle()
            return {"ok": True, "locked": "mIsShowing=true" in self.shell.run("dumpsys window | grep mIsShowing=")}
        return {"ok": True, "locked": False}

    # ---- hands --------------------------------------------------------------------------------

    def execute(self, name: str, args: dict[str, Any], screen: ScreenState) -> dict[str, Any]:
        w, h = self.width, self.height
        sh = self.shell.run
        if name == "click":
            x, y = px(args["x"], w), px(args["y"], h)
            if not self._try("tap", x=x, y=y):
                sh(f"input tap {x} {y}")
        elif name == "long_press":
            x, y, ms = px(args["x"], w), px(args["y"], h), int(float(args.get("seconds", 1.5)) * 1000)
            if not self._try("tap", x=x, y=y, hold_ms=ms):
                sh(f"input swipe {x} {y} {x} {y} {ms}")
        elif name == "drag_and_drop":
            x1, y1, x2, y2 = px(args["start_x"], w), px(args["start_y"], h), px(args["end_x"], w), px(args["end_y"], h)
            if not self._try("swipe", x1=x1, y1=y1, x2=x2, y2=y2, ms=400):
                sh(f"input swipe {x1} {y1} {x2} {y2} 400")
        elif name == "type":
            # The helper replaces the field's text and handles every language; `input text` appends ASCII only.
            text = str(args.get("text", ""))
            r = self._h("set_text", text=text)
            if r and r.get("error") == "password_field":
                return {"ok": False, "error": "password_field"}
            if not (r and r.get("ok")):
                if not text.isascii():
                    return {"ok": False, "error": (r or {}).get("error") or "non_ascii_text_needs_helper"}
                sh(f"input text {shlex.quote(text.replace(' ', '%s'))}")
            if args.get("press_enter") and not self._try("enter"):
                sh("input keyevent 66")
        elif name in ("go_back", "go_home", "press_key"):
            code = 4 if name == "go_back" else 3 if name == "go_home" else KEYS.get(str(args.get("key", "enter")).lower(), 66)
            if not self._try("key", code=code):
                sh(f"input keyevent {code}")
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

    # ---- playbooks ----------------------------------------------------------------------------

    def set_alarm(self, hour: int, minute: int, label: str = "") -> dict[str, Any]:
        """The Clock app's own "set alarm" intent; SKIP_UI sets it without opening any screen."""
        if self._try("set_alarm", hour=int(hour), minute=int(minute), label=label):
            return {"ok": True}  # sent by the helper app, which holds the SET_ALARM permission
        cmd = (f"am start -a android.intent.action.SET_ALARM --ei android.intent.extra.alarm.HOUR {int(hour)} "
               f"--ei android.intent.extra.alarm.MINUTES {int(minute)} --ez android.intent.extra.alarm.SKIP_UI true")
        if label:
            cmd += f" --es android.intent.extra.alarm.MESSAGE {shlex.quote(label)}"
        out = self.shell.run(cmd + " 2>&1")
        if "Permission Denial" in out:
            # The adb shell may not hold SET_ALARM (stock Android doesn't grant it). Opening the alarm
            # list still needs no permission and saves the operator a few steps.
            self.shell.run("am start -a android.intent.action.SHOW_ALARMS >/dev/null 2>&1")
            self.settle()
            return {"ok": False, "error": "no_set_alarm_permission", "opened": "alarms"}
        if "Error" in out or "Exception" in out:
            return {"ok": False, "error": out.strip().splitlines()[-1][:120]}
        return {"ok": True}

    def set_timer(self, seconds: int, label: str = "") -> dict[str, Any]:
        """The Clock app's own "set timer" intent, started at once (SKIP_UI); needs the helper's permission."""
        if self._try("set_timer", seconds=int(seconds), label=label):
            return {"ok": True}
        self.shell.run("am start -a android.intent.action.SHOW_TIMERS >/dev/null 2>&1")
        self.settle()
        return {"ok": False, "error": "no_helper", "opened": "timers"}

    def contacts(self) -> list[tuple[str, str]] | None:
        """(name, number) for every number in the phone's contacts, read on the box only (the adb shell
        may read contacts); None if it can't."""
        out = self.shell.run("content query --uri content://com.android.contacts/data/phones "
                             "--projection display_name:data1 2>&1")
        if out.lstrip().startswith(("Error", "Exception")) or "SecurityException" in out:
            return None
        return [(m.group(1).strip(), m.group(2).strip()) for m in CONTACT_ROW.finditer(out)]

    def _call_state(self) -> int:
        states = re.findall(r"mCallState=(\d)", self.shell.run("dumpsys telephony.registry | grep mCallState"))
        return max((int(x) for x in states), default=0)  # one line per SIM

    def call(self, number: str) -> dict[str, Any]:
        """Starts the call (the adb shell holds CALL_PHONE) and checks the phone really is calling."""
        tel = re.sub(r"[^\d+]", "", number)
        if not tel:
            return {"ok": False, "error": "no_number"}
        self.shell.run(f"am start -a android.intent.action.CALL -d tel:{tel} >/dev/null 2>&1")
        deadline = time.time() + 5
        while time.time() < deadline:
            if self._call_state() == OFFHOOK:
                return {"ok": True}
            time.sleep(0.25)
        # Not started (Android sends emergency numbers to the dialer instead): show the number ready to call.
        self.shell.run(f"am start -a android.intent.action.DIAL -d tel:{tel} >/dev/null 2>&1")
        self.settle()
        return {"ok": False, "error": "call_not_started", "dialer": True}

    def open_chat(self, app: str, number: str, text: str) -> dict[str, Any]:
        """WhatsApp (or SMS) chat with `number` (international digits) and `text` typed in, not sent."""
        text = " ".join(text.split())
        if app == "whatsapp" and self._installed(LINK_APPS["wa.me"]):
            url = f"https://wa.me/{number}?text={quote(text, safe='')}"
            self.shell.run(f"am start -a android.intent.action.VIEW -d {shlex.quote(url)} "
                           f"-p {LINK_APPS['wa.me']} >/dev/null 2>&1")
            used = "whatsapp"
        else:
            self.shell.run(f"am start -a android.intent.action.SENDTO -d sms:+{number} "
                           f"--es sms_body {shlex.quote(text)} >/dev/null 2>&1")
            used = "sms"
        self.settle()
        return {"ok": True, "app": used}

    def recent_activity(self, since_s: int = 3600) -> dict[str, Any]:
        """Missed calls, SMS and messaging-app notifications from the last `since_s` seconds, read on the
        phone: calls by the helper (call-log permission), SMS by the adb shell, the rest from notifications."""
        since_ms = (int(self.shell.run("date +%s").strip() or time.time()) - since_s) * 1000  # the phone's clock
        r = self._h("missed_calls", since_ms=since_ms)
        calls = (r or {}).get("calls", [])
        names = {re.sub(r"\D", "", n)[-10:]: name for name, n in (self.contacts() or [])}
        for c in calls:
            c["name"] = c.get("name") or names.get(re.sub(r"\D", "", c.get("number", ""))[-10:], "")
        out = self.shell.run(f"content query --uri content://sms/inbox --projection address:body:date "
                             f"--where 'date>{since_ms}' --sort 'date DESC' 2>/dev/null")
        messages = [{"app": "SMS", "from": names.get(re.sub(r"\D", "", a)[-10:], a), "text": body, "at": int(at)}
                    for a, body, at in SMS_ROW.findall(out)][:30]
        messages += notification_messages(self.shell.run("dumpsys notification --noredact 2>/dev/null"))
        return {"ok": True, "calls": calls, "messages": messages, "calls_readable": bool(r and r.get("ok"))}

    def open_camera(self) -> dict[str, Any]:
        """The phone's camera, in photo mode. Nothing is saved: the box looks at the live view."""
        out = self.shell.run("am start -a android.media.action.STILL_IMAGE_CAMERA 2>&1")
        self.settle()
        return {"ok": "Error" not in out}

    def photo(self) -> str | None:
        """A sharp look at the screen (for reading small print through the camera), as JPEG base64."""
        r = self._h("screenshot", max_w=1440, quality=85)
        if r and r.get("ok"):
            return r["jpeg_b64"]
        return self._screenshot_b64()

    def play_video(self, query: str) -> dict[str, Any]:
        """YouTube's own "play from search" (what voice assistants use): it usually starts the top result."""
        pkg = KNOWN_APPS["youtube"]
        if not self._installed(pkg):
            return {"ok": False, "error": "not_installed"}
        self.shell.run(f"am start -a android.media.action.MEDIA_PLAY_FROM_SEARCH -p {pkg} "
                       f"--es query {shlex.quote(query)} >/dev/null 2>&1")
        return {"ok": True}

    def media_playing(self, pkg: str) -> bool:
        """True if `pkg` has a media session that is playing (PlaybackState 3)."""
        out = self.shell.run("dumpsys media_session")
        return any(block.startswith(pkg) and "state=PlaybackState {state=3" in block
                   for block in out.split("package=")[1:])

    def set_volume(self, level: str) -> dict[str, Any]:
        """'up' / 'down' / 'max' for ring, notification, media and call volume (helper app); without the
        helper, volume key presses (they change whichever sound is active)."""
        r = self._h("volume", level=level)
        if r and r.get("ok"):
            return {"ok": True, "percent": r["percent"], "unsilenced": bool(r.get("unsilenced"))}
        code = 25 if level == "down" else 24
        self.shell.run(f"input keyevent {' '.join([str(code)] * (15 if level == 'max' else 3))}")
        return {"ok": True}

    def battery(self) -> dict[str, Any]:
        out = self.shell.run("dumpsys battery")
        level, status = re.search(r"level: (\d+)", out), re.search(r"status: (\d+)", out)
        if not level:
            return {"ok": False}
        return {"ok": True, "level": int(level.group(1)), "charging": bool(status and status.group(1) == "2")}

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
        if self.helper:
            self.helper.close()
        self.shell.close()


def notification_messages(dump: str) -> list[dict[str, Any]]:
    """Messages in messaging apps' notifications (dumpsys notification --noredact), newest dump order."""
    messages = []
    for block in dump.split("NotificationRecord(")[1:]:
        pkg = re.search(r"pkg=(\S+)", block)
        app = MESSAGE_APPS.get(pkg.group(1)) if pkg else None
        title = re.search(r"android\.title=\w+ \((.*)\)$", block, re.M)
        text = re.search(r"android\.(?:bigText|text)=\w+ \((.*)\)$", block, re.M)
        if app and title and text and "new messages" not in text.group(1):
            messages.append({"app": app, "from": title.group(1), "text": text.group(1)[:300]})
    return messages[:30]


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
        scroll = a.get("scrollable") == "true"
        if not (text or desc or click or edit or scroll):
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
        if scroll:
            n["scroll"] = True
        if a.get("focused") == "true":
            n["focus"] = True
        nodes.append(n)
    return package, nodes, secure
