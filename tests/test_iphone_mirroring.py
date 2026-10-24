"""The iPhone Mirroring driver, with a stand-in for the Mac helper (no Mac permissions or iPhone needed)."""

import pytest
from test_brain import act, node, screen

from box.brain.brain import screen_text
from box.brain.safety import gate, payment_screen
from box.console import Console
from box.drivers import iphone_mirroring
from box.drivers.base import ScreenState
from box.drivers.iphone_mirroring import (HOME, RETURN, SELECT_ALL, IphoneMirroringDriver, key_codes, nodes_from_ocr,
                                          still)


class FakeHelper:
    def __init__(self, window=None):
        self.window = window or {"ok": True, "id": 7, "accessibility": True}
        self.calls: list[tuple[str, dict]] = []

    def call(self, cmd, **args):
        self.calls.append((cmd, args))
        return self.window if cmd == "window" else {"ok": True}

    def close(self):
        pass


@pytest.fixture(autouse=True)
def no_waiting(monkeypatch):
    monkeypatch.setattr(iphone_mirroring.time, "sleep", lambda s: None)


def driver() -> tuple[IphoneMirroringDriver, FakeHelper]:
    h = FakeHelper()
    d = IphoneMirroringDriver(h)
    d.settle = lambda max_s=2.5: None  # no screen to wait for
    h.calls.clear()
    return d, h


def test_typing_uses_key_codes_with_shift_for_capitals_and_symbols():
    assert key_codes("Hi 5!") == [[4, ["shift"]], [34, []], [49, []], [23, []], [18, ["shift"]]]
    assert key_codes("नमस्ते") is None and key_codes("café") is None


def test_recognised_words_become_tappable_elements_in_pixels():
    lines = [{"text": "Clock", "b": [0.5, 0.4, 0.7, 0.45]}, {"text": " ", "b": [0, 0, 0.1, 0.1]}]
    assert nodes_from_ocr(lines, 600, 1400) == [
        {"i": 0, "cls": "Text", "text": "Clock", "click": True, "b": [300, 560, 420, 630]}]


def test_a_screen_counts_as_still_despite_a_few_moving_pixels():
    a = bytes([100] * 1000)
    assert still(a, bytes([100] * 990 + [200] * 10)) and not still(a, bytes([100] * 500 + [200] * 500))


def test_hands_map_to_clicks_drags_and_keys():
    d, h = driver()
    d.execute("click", {"x": 500, "y": 400}, None)
    d.execute("go_home", {}, None)
    d.execute("go_back", {}, None)
    d.execute("type", {"text": "milk", "press_enter": True}, None)
    assert h.calls[0] == ("click", {"x": 500, "y": 400})
    assert h.calls[1] == ("shortcut", {"code": HOME})
    assert h.calls[2][0] == "drag" and h.calls[2][1]["x1"] < 10  # a swipe from the left edge
    assert h.calls[3] == ("keys", {"keys": SELECT_ALL})
    assert h.calls[4] == ("keys", {"keys": key_codes("milk") + [[RETURN, []]]})


def test_text_the_iphone_cannot_take_is_refused_before_anything_is_pressed():
    d, h = driver()
    assert d.execute("type", {"text": "दूध"}, None) == {"ok": False, "error": "iphone_types_english_only"}
    assert h.calls == []


def test_the_driver_says_what_is_missing():
    with pytest.raises(RuntimeError, match="Open iPhone Mirroring"):
        IphoneMirroringDriver(FakeHelper({"ok": False, "error": "no_iphone_mirroring_window"}))
    with pytest.raises(RuntimeError, match="Accessibility"):
        IphoneMirroringDriver(FakeHelper({"ok": True, "id": 7, "accessibility": False}))


def test_iphone_safety_without_app_names_or_field_information():
    upi = screen(node("Enter UPI PIN"), package="iphone")
    assert payment_screen(upi) and not payment_screen(screen(node("Clock"), package="iphone"))
    login = ScreenState("iphone", 1000, 2000, [node("Password", click=True)], has_secure_field=True)
    assert gate(act("type", 0, "Password", text="hunter2"), login.nodes[0], login, "en-IN")[0] == "private"


def test_the_brain_is_told_how_iphone_screens_differ():
    s = ScreenState("iphone", 1000, 2000, [node("Clock")], hint="iPhone: use x,y for icons.")
    assert screen_text(s).splitlines()[:2] == ["app=iphone", "iPhone: use x,y for icons."]


def test_plan_only_approval_for_testing_on_a_real_phone():
    c = Console(speak=False, plan_only=True)
    assert c.ask("Shall I open Clock?", plan=True) is True
    assert c.ask("Send this to Asha?") is False
