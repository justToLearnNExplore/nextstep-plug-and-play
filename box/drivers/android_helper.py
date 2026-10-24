"""Client for the helper app (helper/) that the box installs on an Android phone over USB.

The helper runs only while the box is connected: it is started with `am instrument -w`, which ends
when adb does, and it answers on a local socket that only adb may use. Compared with plain ADB:
reading the screen ~20 ms instead of ~1.1 s, a tap ~10 ms instead of ~85 ms, typing in any
language, and alarms set in one step. If anything about it fails, the driver uses plain ADB.
"""

import json
import os
import re
import socket
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

PACKAGE = "com.nextstepbox.helper"
VERSION = 1  # must match Box.VERSION in helper/src/com/nextstepbox/helper/Box.java
SOCKET = "nextstep-box-helper"
APK = Path(os.getenv("NEXTSTEP_BOX_HELPER_APK", "")
           or Path(__file__).resolve().parents[2] / "helper" / "build" / "nextstep-box-helper.apk")


class HelperError(RuntimeError):
    pass


class Helper:
    def __init__(self, adb: list[str], shell):
        self.adb, self.shell = adb, shell  # adb = ["adb"] or ["adb", "-s", serial]
        self.proc: subprocess.Popen | None = None
        self.port: int | None = None
        self.sock: socket.socket | None = None
        self.lock = threading.Lock()
        self._install()
        self._launch()

    @classmethod
    def start(cls, adb: list[str], shell) -> "Helper | None":
        try:
            return cls(adb, shell)
        except Exception as e:  # never block the box: plain ADB still works
            print(f"  (helper app not used: {e}; using plain ADB)", flush=True)
            return None

    def _run_adb(self, *args: str, timeout: float = 60) -> str:
        r = subprocess.run([*self.adb, *args], capture_output=True, text=True, timeout=timeout)
        return r.stdout + r.stderr

    def _install(self) -> None:
        out = self.shell.run(f"dumpsys package {PACKAGE} | grep -m1 versionCode")
        m = re.search(r"versionCode=(\d+)", out)
        if m and int(m.group(1)) == VERSION:
            return
        if not APK.exists():
            raise HelperError(f"{APK} is not built (run helper/build.sh)")
        out = self._run_adb("install", "-r", str(APK))
        if "INSTALL_FAILED_UPDATE_INCOMPATIBLE" in out:  # signed with another key: replace it
            self._run_adb("uninstall", PACKAGE)
            out = self._run_adb("install", str(APK))
        if "Success" not in out:
            raise HelperError(f"install failed: {out.strip()[-200:]}")

    def _launch(self) -> None:
        # Starting it again replaces any copy left over from an earlier run.
        self.proc = subprocess.Popen([*self.adb, "shell", f"am instrument -w {PACKAGE}/.Box"],
                                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        self.port = int(self._run_adb("forward", "tcp:0", f"localabstract:{SOCKET}").strip())
        deadline = time.time() + 8
        while time.time() < deadline:
            if self.proc.poll() is not None:
                raise HelperError(f"helper exited: {(self.proc.stdout.read() if self.proc.stdout else '').strip()[-200:]}")
            try:
                self.sock = socket.create_connection(("127.0.0.1", self.port), timeout=2)
                self.file = self.sock.makefile("rwb")
                pong = self.call("ping", timeout=2)
            except OSError:  # adb accepts at once, but the helper may not be listening yet
                self._disconnect()
                time.sleep(0.15)
                continue
            if pong.get("version") != VERSION:
                raise HelperError(f"helper version {pong.get('version')}, expected {VERSION}")
            return
        raise HelperError("helper did not answer")

    def call(self, cmd: str, timeout: float = 15, **args: Any) -> dict[str, Any]:
        with self.lock:
            if not self.sock:
                raise ConnectionError("helper not connected")
            self.sock.settimeout(timeout)
            self.file.write((json.dumps({"cmd": cmd, **args}, ensure_ascii=False) + "\n").encode())
            self.file.flush()
            line = self.file.readline()
        if not line:
            raise ConnectionError("helper closed the connection")
        return json.loads(line)

    def _disconnect(self) -> None:
        if self.sock:
            try:
                self.sock.close()
            except OSError:
                pass
        self.sock = None

    def close(self) -> None:
        try:
            self.call("quit", timeout=2)
        except (OSError, ValueError):
            pass
        self._disconnect()
        if self.proc:
            self.proc.terminate()  # ends `am instrument`, so Android ends the helper too
        if self.port:
            self._run_adb("forward", "--remove", f"tcp:{self.port}", timeout=5)
