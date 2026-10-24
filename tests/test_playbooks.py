"""One-step shortcuts: calls, messages, battery, volume, YouTube and directions, without a phone or Gemini."""

import pytest
from test_brain import FakeConsole, FakeGemini, FakePhone, act, node, plan, runner, screen, turn

from box.brain import playbooks
from box.brain.playbooks import contact_matches, international
from box.brain.safety import gate

CONTACTS = [("Ravi Kumar", "+91 98450 12345"), ("Ravi Sharma", "98861 23456"), ("Asha Rao", "99000 11223"),
            ("रवि बेटा", "097400 55667"), ("Ravi Kumar", "+919845012345")]
HOME = screen(node("Home"))
CHAT = screen(node("Asha Rao"), node("I'll be late", (300, 1800, 900, 1900), edit=True),
              node(b=(900, 1800, 1000, 1900), desc="Send SMS", click=True, id="send_message_button_container"))
SENT = screen(node("Asha Rao"), node("I'll be late", (0, 1000, 1000, 1100)), node(b=(300, 1800, 900, 1900), edit=True),
              node(b=(900, 1800, 1000, 1900), desc="Send SMS", click=True, id="send_message_button_container"))
OUTDATED = screen(node("Update Google Maps to continue"), node("Update app", click=True))


class Clock:
    """Stands in for `time` in playbooks.py, so waiting for a screen takes no real time."""
    def __init__(self):
        self.t = 0.0

    def monotonic(self):
        return self.t

    def sleep(self, s):
        self.t += s


@pytest.fixture(autouse=True)
def no_waiting(monkeypatch):
    monkeypatch.setattr(playbooks, "time", Clock())


class Phone(FakePhone):
    def __init__(self, *screens, contacts=CONTACTS, call_ok=True, playing=False):
        super().__init__(*screens)
        self.book, self.call_ok, self.playing = list(contacts), call_ok, playing
        self.calls, self.chats, self.videos, self.volume = [], [], [], None

    def contacts(self):
        return self.book

    def call(self, number):
        self.calls.append(number)
        return {"ok": True} if self.call_ok else {"ok": False, "error": "call_not_started", "dialer": True}

    def open_chat(self, app, number, text):
        self.chats.append((app, number, text))
        self.pos += 1
        return {"ok": True, "app": "sms"}

    def battery(self):
        return {"ok": True, "level": 63, "charging": True}

    def set_volume(self, level):
        self.volume = level
        return {"ok": True, "percent": 100}

    def play_video(self, query):
        self.videos.append(query)
        self.pos += 1
        return {"ok": True}

    def media_playing(self, pkg):
        return self.playing


def test_contacts_match_whole_names_then_words_one_entry_per_number():
    assert contact_matches(CONTACTS, ["Ravi"]) == [("Ravi Kumar", "+91 98450 12345"), ("Ravi Sharma", "98861 23456")]
    assert contact_matches(CONTACTS, ["Ravi Kumar"]) == [("Ravi Kumar", "+91 98450 12345")]
    names = [n for n, _ in contact_matches(CONTACTS, ["रवि", "Ravi"])]
    assert names == ["Ravi Kumar", "Ravi Sharma", "रवि बेटा"]
    assert contact_matches(CONTACTS, ["asha"]) == [("Asha Rao", "99000 11223")]
    assert contact_matches(CONTACTS, ["sh"]) == [] and contact_matches(CONTACTS, ["Doctor"]) == []


def test_international_numbers_for_whatsapp():
    assert international("+91 98450 12345", "91") == "919845012345"
    assert international("097400 55667", "91") == "919740055667"
    assert international("98861 23456", "91") == "919886123456"
    assert international("0044 20 7946 0000", "91") == "442079460000"
    assert international("919845012345", "91") == "919845012345"


def test_call_asks_once_naming_the_person_and_number():
    phone = Phone(HOME, contacts=[c for c in CONTACTS if c[0] != "Ravi Sharma"])
    con = FakeConsole()
    report = runner(FakeGemini(plan("call", [("contact", "Ravi Kumar")])), phone, con).run("call Ravi")
    assert con.asked == ["Call Ravi Kumar on +91 98450 12345?"]  # not the plan's own question as well
    assert phone.calls == ["+91 98450 12345"]
    assert report.outcome == "done" and report.playbook == "call" and con.said[-1] == "Calling Ravi Kumar."


def test_call_goes_through_the_people_with_that_name_until_one_is_meant():
    phone = Phone(HOME)
    con = FakeConsole(answers=[False, True])
    assert runner(FakeGemini(plan("call", [("contact", "Ravi")])), phone, con).run("call Ravi").outcome == "done"
    assert con.asked == ["Call Ravi Kumar on +91 98450 12345?", "Call Ravi Sharma on 98861 23456?"]
    assert phone.calls == ["98861 23456"]


def test_no_to_everyone_calls_nobody():
    phone = Phone(HOME)
    report = runner(FakeGemini(plan("call", [("contact", "Ravi")])), phone, FakeConsole(answers=[False, False])).run("x")
    assert report.outcome == "declined" and phone.calls == []


def test_call_someone_not_in_contacts():
    phone = Phone(HOME)
    con = FakeConsole()
    report = runner(FakeGemini(plan("call", [("contact", "Doctor")])), phone, con).run("call the doctor")
    assert report.outcome == "not_found" and phone.calls == [] and con.asked == []
    assert con.said == ["I couldn't find Doctor in your contacts."]


def test_call_a_number_that_android_only_puts_on_the_dialer():
    phone = Phone(HOME, call_ok=False)
    con = FakeConsole()
    report = runner(FakeGemini(plan("call", [("number", "112")])), phone, con).run("call 112")
    assert con.asked == ["Call 112?"] and phone.calls == ["112"]
    assert report.outcome == "handed_over" and "green button" in con.said[-1]


def test_a_phone_without_call_support_gets_the_plan_question_and_the_operator():
    g = FakeGemini(plan("call", [("contact", "Ravi")]), turn(done=True, success=True, message="Calling Ravi."))
    con = FakeConsole()
    report = runner(g, FakePhone(HOME), con).run("call Ravi")
    assert con.asked == ["Shall I?"] and report.outcome == "done" and [c[0] for c in g.calls] == ["Plan", "Turn"]


def test_message_is_typed_then_sent_only_after_a_yes():
    phone = Phone(HOME, CHAT, SENT)
    con = FakeConsole()
    p = plan("send_message", [("contact", "Asha"), ("text", "I'll be  late"), ("app", "sms")])
    report = runner(FakeGemini(p), phone, con).run("tell Asha I'll be late")
    assert phone.chats == [("sms", "919900011223", "I'll be late")]
    assert con.asked == ["Send “I'll be late” to Asha Rao on SMS?"]
    assert phone.done == [("click", {"x": 950, "y": 925})]  # the Send button
    assert report.outcome == "done" and con.said[-1] == "Sent to Asha Rao."


def test_message_not_sent_when_the_user_says_no():
    phone = Phone(HOME, CHAT, SENT)
    p = plan("send_message", [("contact", "Asha"), ("text", "I'll be late")])
    report = runner(FakeGemini(p), phone, FakeConsole(answers=[False])).run("x")
    assert report.outcome == "declined_step" and phone.done == []


def test_message_asks_which_person_when_several_match():
    phone = Phone(HOME, screen(node("Ravi Sharma"), *CHAT.nodes[1:]), SENT)
    con = FakeConsole(answers=[False, True, True])
    p = plan("send_message", [("contact", "Ravi"), ("text", "I'll be late")])
    assert runner(FakeGemini(p), phone, con).run("x").outcome == "done"
    assert con.asked[:2] == ["Do you mean Ravi Kumar?", "Do you mean Ravi Sharma?"]
    assert phone.chats[0][1] == "919886123456"


def test_battery_is_said_without_a_question():
    con = FakeConsole()
    report = runner(FakeGemini(plan("battery")), Phone(HOME), con).run("how much battery")
    assert con.asked == [] and report.outcome == "done"
    assert con.said == ["Your battery is at 63 percent. It is charging."]


def test_volume_says_the_new_level():
    phone = Phone(HOME)
    con = FakeConsole()
    report = runner(FakeGemini(plan("volume", [("level", "max")])), phone, con).run("I can't hear my phone")
    assert phone.volume == "max" and report.outcome == "done" and con.said[-1] == "The volume is now at 100 percent."


def test_video_that_starts_playing_needs_no_operator():
    phone = Phone(HOME, screen(node("Hanuman Chalisa")), playing=True)
    g = FakeGemini(plan("play_video", [("query", "Hanuman Chalisa")]))
    report = runner(g, phone).run("play Hanuman Chalisa")
    assert phone.videos == ["Hanuman Chalisa"] and report.outcome == "done" and len(g.calls) == 1


def test_an_app_that_must_be_updated_first_is_reported():
    phone = Phone(HOME, OUTDATED)
    con = FakeConsole()
    report = runner(FakeGemini(plan("play_video", [("query", "bhajans")])), phone, con).run("play bhajans")
    assert report.outcome == "app_outdated" and "needs an update" in con.said[-1]


def test_video_falls_back_to_youtube_search_for_the_operator():
    g = FakeGemini(plan("play_video", [("query", "old songs")]), turn(done=True, success=True, message="Playing."))
    phone = FakePhone(HOME, HOME)
    assert runner(g, phone).run("play old songs").outcome == "done"
    assert phone.done[0] == ("open_link", {"url": "https://www.youtube.com/results?search_query=old+songs"})


def test_directions_open_maps_with_the_route():
    route = screen(node("25 min"), node("6.2 km"), node("Start", click=True), package="com.google.android.apps.maps")
    phone = FakePhone(HOME, route)
    g = FakeGemini(plan("directions", [("place", "Lalbagh, Bengaluru"), ("mode", "walking")]))
    assert runner(g, phone).run("how do I get to Lalbagh").outcome == "done" and len(g.calls) == 1
    assert phone.done == [("open_link", {"url": "https://www.google.com/maps/dir/?api=1&destination=Lalbagh%2C+Bengaluru"
                                                "&travelmode=walking"})]


def test_directions_with_an_outdated_maps_app():
    con = FakeConsole()
    report = runner(FakeGemini(plan("directions", [("place", "Lalbagh")])), FakePhone(HOME, OUTDATED), con).run("x")
    assert report.outcome == "app_outdated" and con.said[-1].startswith("Google Maps on this phone needs an update")


def test_tapping_call_asks_first_but_call_history_does_not():
    s = screen(node(desc="Make a call", click=True), node("Call history", click=True), node(desc="End call", click=True),
               node(desc="dial pad", click=True), node(desc="Voice call", click=True))
    assert gate(act("tap", 0, "Make a call"), s.nodes[0], s, "en-IN")[0] == "confirm"
    assert gate(act("tap", 1, "Call history", intent="Open history"), s.nodes[1], s, "en-IN")[0] == "auto"
    assert gate(act("tap", 2, "End call", intent="Hang up"), s.nodes[2], s, "en-IN")[0] == "auto"
    assert gate(act("tap", 3, "dial pad", intent="Open keypad"), s.nodes[3], s, "en-IN")[0] == "auto"
    assert gate(act("tap", 4, "Voice call"), s.nodes[4], s, "en-IN")[0] == "confirm"


def test_web_search_waits_for_the_results_before_the_operator_looks():
    loading = screen(node("Google Search"), node("google.com/search?q=weather", edit=True))
    results = screen(node("weather today - Google Search"), node("22°C"), node("Cloudy"),
                     *[node(f"result {i}") for i in range(12)])
    g = FakeGemini(plan("web_search", [("query", "weather today")]),
                   turn(done=True, success=True, message="It is 22°C and cloudy."))

    class SlowPage(FakePhone):
        looks = 0

        def capture(self, with_screenshot):
            self.looks += 1
            self.pos = 1 if self.looks < 3 else 2  # the page appears on the third look
            return super().capture(with_screenshot)

    phone = SlowPage(HOME, loading, results)
    assert runner(g, phone).run("weather today?").outcome == "done"
    assert "22°C" in g.calls[1][1][0]  # the operator's first look already had the results
