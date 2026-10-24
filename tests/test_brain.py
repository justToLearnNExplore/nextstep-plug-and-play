"""The box's own brain and agent loop, run against a fake Gemini and a scripted fake phone."""

from box.brain.brain import Brain, screen_text
from box.brain.safety import gate
from box.brain.schemas import Action, Param, Plan, Turn
from box.config import Config
from box.drivers.base import ScreenState
from box.runner import Runner, find_by_label


def node(text="", b=(0, 0, 100, 100), **flags):
    n = {"b": list(b), **flags}
    if text:
        n["text"] = text
    return n


def screen(*nodes, package="com.example") -> ScreenState:
    return ScreenState(package=package, width=1000, height=2000, nodes=list(nodes))


def act(kind="tap", element=-1, label="", text="", expect="", irreversible=False, intent="") -> Action:
    return Action(kind=kind, element=element, label=label, x=-1, y=-1, text=text, press_enter=False,
                  direction="none", intent=intent or f"{kind} {label}", announce=False, expect=expect,
                  irreversible=irreversible)


def plan(playbook="none", params=(), goal="do it") -> Plan:
    return Plan(summary="Shall I?", steps=["a"], refused=False, app="", playbook=playbook,
                params=[Param(name=k, value=v) for k, v in params], goal=goal, done_message="All set.")


def turn(*actions, done=False, success=False, message="", need_screenshot=False) -> Turn:
    return Turn(need_screenshot=need_screenshot, actions=list(actions), done=done, success=success, message=message)


class FakeGemini:
    def __init__(self, *answers):
        self.answers = list(answers)
        self.calls: list[tuple[str, list]] = []

    def structured(self, models, system, parts, schema, thinking="LOW"):
        self.calls.append((schema.__name__, parts))
        answer = self.answers.pop(0)
        assert isinstance(answer, schema), f"expected {schema.__name__}, got {type(answer).__name__}"
        return answer


class FakePhone:
    """Each executed action moves to the next scripted screen."""
    name = "fake"

    def __init__(self, *screens):
        self.screens = list(screens)
        self.pos = 0
        self.done: list[tuple[str, dict]] = []
        self.alarms: list[tuple[int, int, str]] = []

    def capture(self, with_screenshot):
        s = self.screens[min(self.pos, len(self.screens) - 1)]
        return ScreenState(s.package, s.width, s.height, s.nodes, "SHOT" if with_screenshot else None, with_screenshot)

    def execute(self, name, args, screen):
        self.done.append((name, args))
        self.pos += 1
        return {"ok": True}

    def set_alarm(self, hour, minute, label=""):
        self.alarms.append((hour, minute, label))
        return {"ok": True}

    def set_timer(self, seconds, label=""):
        self.alarms.append(("timer", seconds, label))
        return {"ok": True}

    def close(self):
        pass


class FakeConsole:
    def __init__(self, answers=()):
        self.answers = list(answers)
        self.asked: list[str] = []
        self.said: list[str] = []

    def status(self, text, speak=False):
        pass

    def say(self, text):
        self.said.append(text)

    def timing(self, t):
        pass

    def finish_speaking(self):
        pass

    def speak_now(self, text):
        self.said.append(text)

    def ask(self, question, details=None, yes="Yes", no="No", plan=False):
        self.asked.append(question)
        return self.answers.pop(0) if self.answers else True


def runner(gemini, phone, console=None):
    return Runner(Config(), Brain(gemini), phone, console or FakeConsole(), trace=False)


HOME = screen(node("Search", (0, 0, 1000, 200), click=True, edit=True), node("Cart", (800, 1800, 1000, 2000), click=True))
TYPED = screen(node("milk", (0, 0, 1000, 200), edit=True, focus=True))
RESULTS = screen(node("Amul Milk 1 L", (0, 400, 700, 600)), node("ADD", (700, 400, 1000, 600), click=True))
ADDED = screen(node("Amul Milk 1 L", (0, 400, 700, 600)), node("1", (700, 400, 1000, 600)), node("View cart", click=True))


def test_screen_text_numbers_elements_in_0_999():
    text = screen_text(HOME)
    assert "[0] 'Search' tap input @500,50" in text
    assert "[1] 'Cart' tap @900,950" in text


def test_find_by_label_prefers_exact_then_nearest():
    s = screen(node("Add to cart", (0, 0, 10, 10)), node("ADD", (0, 900, 10, 910)), node("ADD", (0, 100, 10, 110)))
    assert find_by_label(s, "add", near=(5, 50))["b"][1] == 100
    assert find_by_label(s, "add to") ["text"] == "Add to cart"
    assert find_by_label(s, "zz") is None


def test_gates():
    s = screen(node("Place order ₹62", click=True))
    assert gate(act("tap", 0, "Place order ₹62"), s.nodes[0], s, "en-IN")[0] == "confirm"
    assert gate(act("tap", 0, "Next", irreversible=True), s.nodes[0], s, "en-IN")[0] == "confirm"
    perm = screen(node("Allow", click=True), node("Accept & continue", click=True))
    assert gate(act("tap", 0, "Allow"), perm.nodes[0], perm, "en-IN")[0] == "confirm"
    assert gate(act("tap", 1, "Accept & continue"), perm.nodes[1], perm, "en-IN")[0] == "confirm"
    pw = screen(node(edit=True, focus=True, secure=True))
    assert gate(act("type", 0, text="1234"), pw.nodes[0], pw, "en-IN")[0] == "private"
    otp = screen(node("Enter OTP", edit=True, focus=True))
    assert gate(act("type", 0, text="1234"), otp.nodes[0], otp, "en-IN")[0] == "private"
    assert gate(act("open_link", text="https://evil.example/x"), None, s, "en-IN")[0] == "blocked"
    assert gate(act("open_link", text="https://blinkit.com/s/?q=milk"), None, s, "en-IN")[0] == "auto"
    paytm = screen(node("Pay", click=True), package="net.one97.paytm")
    assert gate(act("tap", 0, "OK"), paytm.nodes[0], paytm, "en-IN")[0] == "private"


def test_batch_is_checked_on_the_box_with_one_brain_call():
    g = FakeGemini(
        plan(),
        turn(act("type", 0, "Search", text="milk", expect="milk"),
             act("tap", 1, "ADD", expect="View cart")),  # index 1 is from HOME; the box must find ADD by label
        turn(done=True, success=True, message="Milk is in your cart."),
    )
    # type = click (focus field) + type -> two executes before the next screen
    phone = FakePhone(HOME, HOME, RESULTS, ADDED)
    con = FakeConsole()
    report = runner(g, phone, con).run("add milk")
    assert report.outcome == "done"
    assert [c[0] for c in g.calls] == ["Plan", "Turn", "Turn"]
    assert phone.done[0] == ("click", {"x": 500, "y": 50})
    assert phone.done[1] == ("type", {"text": "milk", "press_enter": False})
    assert phone.done[2] == ("click", {"x": 850, "y": 250})  # ADD on RESULTS, not 'Cart' on HOME
    assert sum(s.checked for s in report.steps) == 2
    assert con.said[-1] == "Milk is in your cart."


def test_unexpected_screen_stops_the_batch_and_tells_the_brain():
    g = FakeGemini(plan(), turn(act("tap", 1, "Cart", expect="Checkout"), act("tap", -1, "Pay")),
                   turn(done=True, success=False, message=""))
    phone = FakePhone(HOME, RESULTS)
    con = FakeConsole()
    report = runner(g, phone, con).run("x")
    assert len(phone.done) == 1  # 'Pay' never ran
    note_parts = g.calls[2][1][0]
    assert "'Checkout' is not on the screen" in note_parts and "rest of your actions were skipped" in note_parts
    assert report.outcome == "not_possible"
    assert "Nothing was ordered or sent" in con.said[-1]


def test_irreversible_tap_asks_and_no_means_stop():
    order = screen(node("Place order", (0, 1800, 1000, 2000), click=True))
    g = FakeGemini(plan(), turn(act("tap", 0, "Place order", intent="Order milk for ₹62.")))
    phone = FakePhone(order)
    con = FakeConsole(answers=[True, False])  # yes to the plan, no to the order
    report = runner(g, phone, con).run("order milk")
    assert report.outcome == "declined_step"
    assert phone.done == []
    assert con.asked[-1].startswith("Order milk for ₹62.")


def test_an_action_that_changes_nothing_is_reported_then_stopped():
    class StuckPhone(FakePhone):
        def execute(self, name, args, screen):
            self.done.append((name, args))
            return {"ok": True}  # the screen never changes

    same = turn(act("tap", 1, "Cart"))
    g = FakeGemini(plan(), same, same, same)
    phone = StuckPhone(HOME)
    report = runner(g, phone).run("x")
    assert report.outcome == "stuck"
    assert len(phone.done) == 3
    assert "changed nothing" in g.calls[2][1][0]


def test_repeating_an_action_that_did_work_is_allowed():
    # tap '5' -> display changes; delete -> back to the start; tap '5' again must not count as a loop
    pad = lambda shown: screen(node(shown), node("Delete", (800, 0, 1000, 100), click=True),
                               node("5", (400, 900, 600, 1100), click=True))
    g = FakeGemini(plan(), turn(act("tap", 2, "5")), turn(act("tap", 1, "Delete")), turn(act("tap", 2, "5")),
                   turn(done=True, success=True, message="ok"))
    phone = FakePhone(pad("00:00"), pad("00:05"), pad("00:00"), pad("00:05"))
    assert runner(g, phone).run("x").outcome == "done"


def test_unexpected_result_note_says_what_appeared():
    g = FakeGemini(plan(), turn(act("tap", 1, "Cart", expect="Checkout")), turn(done=True, success=False))
    runner(g, FakePhone(HOME, RESULTS)).run("x")
    assert "New on screen: 'Amul Milk 1 L', 'ADD'" in g.calls[2][1][0]


def test_keypad_backspace_is_not_treated_as_deleting_data():
    keys = [node(str(d), click=True) for d in range(10)]
    pad = screen(node("Delete", click=True), *keys)
    assert gate(act("tap", 0, "Delete"), pad.nodes[0], pad, "en-IN")[0] == "auto"
    chat = screen(node("Delete", click=True))
    assert gate(act("tap", 0, "Delete"), chat.nodes[0], chat, "en-IN")[0] == "confirm"


def test_screen_text_skips_labels_that_repeat_their_button():
    tabs = screen(node("Timer", (500, 0, 700, 100), click=True), node("Timer", (520, 20, 680, 80)))
    assert screen_text(tabs).count("'Timer'") == 1


def test_alarm_playbook_skips_the_operator():
    g = FakeGemini(plan("set_alarm", [("hour", "7"), ("minute", "0"), ("label", "Walk")]))
    phone = FakePhone(HOME)
    con = FakeConsole()
    report = runner(g, phone, con).run("alarm 7 am")
    assert phone.alarms == [(7, 0, "Walk")]
    assert len(g.calls) == 1 and report.outcome == "done" and report.playbook == "set_alarm"
    assert con.said[-1] == "All set."


def test_timer_playbook_skips_the_operator():
    g = FakeGemini(plan("set_timer", [("seconds", "300")]))
    phone = FakePhone(HOME)
    report = runner(g, phone).run("5 minute timer")
    assert phone.alarms == [("timer", 300, "")] and len(g.calls) == 1 and report.outcome == "done"


def test_payment_app_is_never_sent_to_the_brain():
    paytm = screen(node("Pay ₹100", click=True), package="net.one97.paytm")
    g = FakeGemini(plan(), turn(done=True, success=True, message="ok"))
    phone = FakePhone(paytm, HOME)
    con = FakeConsole(answers=[True, False])  # approve the plan, then "Stop" at the payment app
    report = runner(g, phone, con).run("x")
    assert report.outcome == "stopped_by_user"
    assert [c[0] for c in g.calls] == ["Plan"]


def test_a_sleeping_locked_phone_is_woken_and_the_user_unlocks_it():
    class LockedPhone(FakePhone):
        wakes = 0

        def wake(self):
            self.wakes += 1
            return {"ok": True, "locked": self.wakes == 1}

    g = FakeGemini(plan("set_alarm", [("hour", "7")]))
    phone = LockedPhone(HOME)
    con = FakeConsole(answers=[True, True])
    assert runner(g, phone, con).run("alarm").outcome == "done"
    assert con.asked[0] == "Please unlock your phone, then say done or press the button." and phone.alarms == [(7, 0, "")]
    stop = FakeConsole(answers=[False])
    assert runner(FakeGemini(), LockedPhone(HOME), stop).run("alarm").outcome == "stopped_by_user"


def test_html_entities_from_the_model_are_not_read_aloud():
    g = FakeGemini(plan(), turn(done=True, success=True, message="It is 21&deg;C &amp; cloudy."))
    con = FakeConsole()
    runner(g, FakePhone(HOME), con).run("weather")
    assert con.said[-1] == "It is 21°C & cloudy."
