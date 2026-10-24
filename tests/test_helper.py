"""The box ↔ helper app connection, without a phone."""

import json
import re
import socket
import threading
from pathlib import Path

import pytest

from box.drivers import android_helper
from box.drivers.android_helper import Helper


def connected_helper() -> tuple[Helper, socket.socket]:
    box_end, phone_end = socket.socketpair()
    h = Helper.__new__(Helper)  # skip install/launch: no phone here
    h.sock, h.file, h.lock = box_end, box_end.makefile("rwb"), threading.Lock()
    return h, phone_end


def test_requests_are_one_json_line_each_and_keep_any_language():
    h, phone = connected_helper()

    def phone_side():
        f = phone.makefile("rwb")
        req = json.loads(f.readline())
        f.write((json.dumps({"ok": True, "echo": req}, ensure_ascii=False) + "\n").encode())
        f.flush()

    threading.Thread(target=phone_side).start()
    assert h.call("set_text", text="सुबह की सैर ಬೆಳಗಿನ")["echo"] == {"cmd": "set_text", "text": "सुबह की सैर ಬೆಳಗಿನ"}


def test_a_closed_helper_is_reported_so_the_driver_can_fall_back():
    h, phone = connected_helper()
    phone.close()
    with pytest.raises(OSError):
        h.call("dump")


def test_box_and_helper_versions_match():
    java = Path(__file__).resolve().parents[1] / "helper/src/com/nextstepbox/helper/Box.java"
    assert int(re.search(r"static final int VERSION = (\d+);", java.read_text()).group(1)) == android_helper.VERSION
