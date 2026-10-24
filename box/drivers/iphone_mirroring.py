"""A real iPhone through macOS iPhone Mirroring: the nearest thing to the box that runs on a Mac.

The box will see an iPhone only as a picture (AirPlay / USB-C video) and work it as a mouse and
keyboard. iPhone Mirroring (macOS 15+, iOS 18+) gives a Mac exactly that, so the same brain can be
tried on a real iPhone before there is hardware:

Eyes   the iPhone Mirroring window, captured with `screencapture -l` (~0.1 s); the words on it and
       where they are come from Apple's text recognition on the Mac. Every look includes the
       screenshot, because many iPhone buttons are icons without words. The Mac reads English and
       other Latin-script languages, not Hindi or Kannada (the brain reads those from the screenshot).
Hands  clicks and drags into the window (taps and swipes), key codes for typing, ⌘1 Home, ⌘2 app
       switcher, ⌘3 Spotlight. iPhone Mirroring passes key codes on but not typed characters or
       pasting, so only text a US keyboard can type works (English letters, digits, symbols).

The Mac side is a small Swift program (iphone_mirroring_helper.swift), built on first use into
~/.nextstep-box/. The app that runs the box needs Screen Recording and Accessibility. While the box
works, the Mac's mouse pointer is the box's.
"""

import base64
import hashlib
import io
import json
import os
import re
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from PIL import Image

from .base import ScreenState

STATE = Path(os.path.expanduser(os.getenv("NEXTSTEP_BOX_STATE", "~/.nextstep-box")))
SOURCE = Path(__file__).with_name("iphone_mirroring_helper.swift")
HINT = ("iPhone (seen through iPhone Mirroring): the list is the words read from the screenshot, so buttons that "
        "are only icons are not in it; use x,y from the screenshot for them. To open an app use kind=open_app: on the "
        "home screen an app's name under its icon can't be tapped (the icon above it can). Go back with the '<' at "
        "the top left or kind=back (a swipe from the left edge). Typing works for English letters, digits and symbols.")
# A screen that shows a password, PIN or OTP: no screenshot goes to the brain, and typing is the user's.
SECRET = re.compile(r"password|passcode|\bpin\b|\botp\b|one.?time|cvv|card number", re.I)

# macOS key codes (US layout). iPhone Mirroring sends the key, so Shift makes capitals and symbols.
_PLAIN = {**dict(zip("asdfhgzxcv", [0, 1, 2, 3, 4, 5, 6, 7, 8, 9])), **dict(zip("bqweryt", [11, 12, 13, 14, 15, 16, 17])),
          "1": 18, "2": 19, "3": 20, "4": 21, "6": 22, "5": 23, "=": 24, "9": 25, "7": 26, "-": 27, "8": 28, "0": 29,
          "]": 30, "o": 31, "u": 32, "[": 33, "i": 34, "p": 35, "l": 37, "j": 38, "'": 39, "k": 40, ";": 41, "\\": 42,
          ",": 43, "/": 44, "n": 45, "m": 46, ".": 47, " ": 49, "`": 50}
_SHIFTED = {"!": "1", "@": "2", "#": "3", "$": "4", "%": "5", "^": "6", "&": "7", "*": "8", "(": "9", ")": "0",
            "_": "-", "+": "=", "{": "[", "}": "]", "|": "\\", ":": ";", '"': "'", "<": ",", ">": ".", "?": "/", "~": "`"}
RETURN, DELETE, ESCAPE = 36, 51, 53
SELECT_ALL, ADDRESS_BAR = [[0, ["cmd"]]], [[37, ["cmd"]]]  # ⌘A, ⌘L, passed on to the iPhone
HOME, APP_SWITCHER, SPOTLIGHT = 18, 19, 20  # iPhone Mirroring's own ⌘1, ⌘2, ⌘3


def key_codes(text: str) -> list[list[Any]] | None:
    """[[code, mods], ...] that type `text`, or None if a character can't be typed this way."""
    keys: list[list[Any]] = []
    for ch in text:
        if ch in _PLAIN:
            keys.append([_PLAIN[ch], []])
        elif ch.isascii() and ch.isalpha():
            keys.append([_PLAIN[ch.lower()], ["shift"]])
        elif ch in _SHIFTED:
            keys.append([_PLAIN[_SHIFTED[ch]], ["shift"]])
        else:
            return None
    return keys


def nodes_from_ocr(lines: list[dict[str, Any]], width: int, height: int) -> list[dict[str, Any]]:
    """Recognised words -> the box's element format (pixel bounds). Each may be tapped: the Mac can't tell."""
    nodes = []
    for line in lines:
        text = str(line.get("text", "")).strip()
        x0, y0, x1, y1 = line["b"]
        if not text:
            continue
        nodes.append({"i": len(nodes), "cls": "Text", "text": text[:200], "click": True,
                      "b": [int(x0 * width), int(y0 * height), int(x1 * width), int(y1 * height)]})
    return nodes


def still(a: bytes, b: bytes, tolerance: float = 1.5) -> bool:
    """Two small grey thumbnails differ by less than `tolerance` grey levels per pixel on average."""
    return len(a) == len(b) and sum(abs(x - y) for x, y in zip(a, b)) / max(len(a), 1) < tolerance


def helper_binary() -> Path:
    """The Swift helper, built once per version of its source."""
    out = STATE / f"mirror-helper-{hashlib.sha256(SOURCE.read_bytes()).hexdigest()[:10]}"
    if not out.exists():
        STATE.mkdir(parents=True, exist_ok=True)
        r = subprocess.run(["swiftc", "-O", "-o", str(out), str(SOURCE)], capture_output=True, text=True, timeout=300)
        if r.returncode != 0:
            raise RuntimeError(f"could not build the iPhone Mirroring helper: {r.stderr.strip()[-300:]}")
    return out


class MirrorHelper:
    def __init__(self):
        self.proc = subprocess.Popen([str(helper_binary())], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     text=True, bufsize=1)

    def call(self, cmd: str, **args: Any) -> dict[str, Any]:
        assert self.proc.stdin and self.proc.stdout
        self.proc.stdin.write(json.dumps({"cmd": cmd, **args}, ensure_ascii=False) + "\n")
        self.proc.stdin.flush()
        line = self.proc.stdout.readline()
        if not line:
            raise RuntimeError("the iPhone Mirroring helper stopped")
        return json.loads(line)

    def close(self) -> None:
        self.proc.terminate()


class IphoneMirroringDriver:
    name = "iphone-mirroring"

    def __init__(self, helper: MirrorHelper | None = None):
        self.helper = helper or MirrorHelper()
        w = self.helper.call("window")
        if not w.get("ok"):
            raise RuntimeError("Open iPhone Mirroring on this Mac first (it shows the iPhone's screen in a window).")
        if not w.get("accessibility"):
            raise RuntimeError("Allow Accessibility for the app that runs the box (System Settings → Privacy & "
                               "Security → Accessibility), so it can click and type into iPhone Mirroring.")
        self.window_id = int(w["id"])
        self.shot = Path(tempfile.gettempdir()) / f"nextstep-iphone-{os.getpid()}.png"
        self.width, self.height = 0, 0

    # ---- eyes ---------------------------------------------------------------------------------

    def _grab(self) -> Image.Image:
        for attempt in range(2):  # a capture now and then fails while the window redraws
            w = self.helper.call("window")  # the window may have moved, or been closed and opened again
            if w.get("ok"):
                self.window_id = int(w["id"])
            r = subprocess.run(["screencapture", "-x", "-o", "-l", str(self.window_id), str(self.shot)],
                               capture_output=True, text=True, timeout=10)
            if r.returncode == 0 and self.shot.exists():
                break
            time.sleep(0.5)
        else:
            raise RuntimeError("Could not capture iPhone Mirroring: allow Screen Recording for the app that runs "
                               "the box, and keep the window open.")
        img = Image.open(self.shot).convert("RGB")
        self.width, self.height = img.size
        return img

    def capture(self, with_screenshot: bool) -> ScreenState:
        img = self._grab()
        ocr = self.helper.call("ocr", path=str(self.shot))
        nodes = nodes_from_ocr(ocr.get("lines", []), self.width, self.height) if ocr.get("ok") else []
        self.shot.unlink(missing_ok=True)  # the iPhone's screen never stays on the Mac's disk
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=60)
        return ScreenState(package="iphone", width=self.width, height=self.height, nodes=nodes,
                           screenshot_b64=base64.b64encode(buf.getvalue()).decode(), screenshot_tried=True,
                           has_secure_field=any(SECRET.search(n["text"]) for n in nodes), hint=HINT)

    def _thumb(self) -> bytes:
        img = self._grab().convert("L").resize((30, 66))
        self.shot.unlink(missing_ok=True)
        return img.tobytes()

    def settle(self, max_s: float = 2.5) -> None:
        """Returns once two looks in a row are nearly the same (the screen stopped moving), at most max_s.
        Nearly: widgets (rain on the weather, a ticking clock) never stop moving entirely."""
        time.sleep(0.15)
        deadline, last = time.time() + max_s, self._thumb()
        while time.time() < deadline:
            time.sleep(0.1)
            now = self._thumb()
            if still(last, now):
                return
            last = now

    # ---- hands --------------------------------------------------------------------------------

    def _keys(self, keys: list[list[Any]]) -> dict[str, Any]:
        return self.helper.call("keys", keys=keys)

    def _shortcut(self, code: int) -> dict[str, Any]:
        return self.helper.call("shortcut", code=code)

    def _clear(self) -> None:
        """Selects what the focused field holds, so the next keys replace it (⌘A needs a moment)."""
        self._keys(SELECT_ALL)
        time.sleep(0.3)

    def _type(self, text: str, press_enter: bool = False) -> dict[str, Any]:
        keys = key_codes(text)
        if keys is None:
            return {"ok": False, "error": "iphone_types_english_only"}
        return self._keys(keys + ([[RETURN, []]] if press_enter else []))

    def execute(self, name: str, args: dict[str, Any], screen: ScreenState | None) -> dict[str, Any]:
        call = self.helper.call
        if name == "click":
            res = call("click", x=args["x"], y=args["y"])
        elif name == "long_press":
            res = call("click", x=args["x"], y=args["y"], hold_ms=int(float(args.get("seconds", 1.0)) * 1000))
        elif name == "drag_and_drop":
            res = call("drag", x1=args["start_x"], y1=args["start_y"], x2=args["end_x"], y2=args["end_y"], ms=350)
        elif name == "type":
            # Replaces what the field holds, like the Android helper: select all, then type over it.
            text = str(args.get("text", ""))
            if key_codes(text) is None:
                return {"ok": False, "error": "iphone_types_english_only"}
            self._clear()
            res = self._type(text, bool(args.get("press_enter")))
        elif name == "press_key":
            res = self._keys([[RETURN, []]])
        elif name == "go_back":
            res = call("drag", x1=3, y1=450, x2=700, y2=450, ms=300)  # the iPhone's swipe from the left edge
        elif name == "go_home":
            res = self._shortcut(HOME)
        elif name == "open_app":
            res = self._spotlight(str(args.get("app_name", "")))
        elif name == "open_link":
            res = self._open_link(str(args["url"]))
        elif name == "wait":
            self.settle(min(float(args.get("seconds", 1)), 5.0))
            return {"ok": True}
        elif name == "take_screenshot":
            return {"ok": True}
        else:
            return {"ok": False, "error": f"unsupported_action:{name}"}
        if res.get("ok"):
            self.settle()
        return res

    def _spotlight(self, query: str) -> dict[str, Any]:
        """Opens what Spotlight finds first for `query` (an app name), like ⌘3 + typing + Return."""
        if key_codes(query) is None:
            return {"ok": False, "error": "iphone_types_english_only"}
        self._shortcut(HOME)
        self.settle()
        self._shortcut(SPOTLIGHT)
        self.settle()
        self._clear()  # Spotlight may still hold the last search
        self._keys([[DELETE, []]])
        self._type(query)
        self._wait_for_words({"Top Hit"}, 2.5)  # Return before Spotlight has its best match does nothing
        res = self._keys([[RETURN, []]])
        self.settle()
        if self._wait_for_words({"Top Hit"}, 0):  # still in Spotlight: once more
            res = self._keys([[RETURN, []]])
            self.settle()
        return res

    def _wait_for_words(self, words: set[str], timeout_s: float) -> bool:
        """True once one of `words` is on the screen (looks every ~0.3 s until timeout_s)."""
        deadline = time.time() + timeout_s
        while True:
            self._grab()
            ocr = self.helper.call("ocr", path=str(self.shot))
            self.shot.unlink(missing_ok=True)
            if any(line.get("text") in words for line in ocr.get("lines", [])):
                return True
            if time.time() >= deadline:
                return False
            time.sleep(0.15)

    def _open_link(self, url: str) -> dict[str, Any]:
        """Safari, its address bar (⌘L), the link, Return."""
        if key_codes(url) is None:
            return {"ok": False, "error": "iphone_types_english_only"}
        res = self._spotlight("Safari")
        if not res.get("ok"):
            return res
        self.settle()
        self._keys(ADDRESS_BAR)
        time.sleep(0.5)
        return self._type(url, press_enter=True)

    def close(self) -> None:
        self.shot.unlink(missing_ok=True)
        self.helper.close()
