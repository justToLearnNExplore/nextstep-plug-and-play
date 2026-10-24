"""Features rebuilt from NextStep for the box: explain my screen, phone help, scam check, pop-ups."""

from test_brain import HOME, FakeConsole, FakeGemini, FakePhone, node, plan, runner, screen

from box.brain.schemas import Explanation


def test_explain_my_screen_needs_no_question_and_offers_a_way_out_of_danger():
    kyc = screen(node("Your KYC has expired"), node("Enter UPI PIN", edit=True), package="com.android.chrome")
    g = FakeGemini(plan("explain_screen"), Explanation(
        explanation="This page asks for your UPI PIN. Never share it.", risk="danger", suggest="back"))
    phone = FakePhone(kyc)
    con = FakeConsole(answers=[True])
    report = runner(g, phone, con).run("what is this?")
    assert report.outcome == "done" and con.said[0] == "This page asks for your UPI PIN. Never share it."
    assert con.asked == ["Shall I take you back?"] and phone.done == [("go_back", {})]
    assert g.calls[1][0] == "Explanation" and len(g.calls[1][1]) == 2  # with the screenshot


def test_a_harmless_screen_is_only_explained():
    g = FakeGemini(plan("explain_screen"), Explanation(explanation="This is your home screen.", risk="none", suggest="none"))
    phone = FakePhone(HOME)
    con = FakeConsole()
    assert runner(g, phone, con).run("what's this").outcome == "done"
    assert con.asked == [] and phone.done == [] and con.said == ["This is your home screen."]


DUMP = """  NotificationRecord(0x1: pkg=com.whatsapp user=UserHandle{0} id=1 tag=null importance=4 key=x
          android.title=String (Ravi Kumar)
          android.text=String (Your OTP is 482913, call me when free)
  NotificationRecord(0x2: pkg=com.google.android.apps.messaging user=UserHandle{0} id=0 tag=sms
          android.title=String (Asha)
          android.text=String (Hello)
  NotificationRecord(0x3: pkg=com.whatsapp user=UserHandle{0} id=2 tag=null importance=4 key=y
          android.title=String (WhatsApp)
          android.text=String (5 new messages)
"""


def test_message_notifications_are_read_from_messaging_apps_only():
    from box.drivers.android_adb import notification_messages
    assert notification_messages(DUMP) == [
        {"app": "WhatsApp", "from": "Ravi Kumar", "text": "Your OTP is 482913, call me when free"}]


class MissedPhone(FakePhone):
    def recent_activity(self, since_s=3600):
        return {"ok": True, "calls": [{"number": "9845012345", "name": "Ravi Kumar", "at": 0}],
                "messages": [{"app": "WhatsApp", "from": "Ravi Kumar", "text": "Your OTP is 482913, call me"}]}


def test_what_did_i_miss_is_said_without_a_question_and_codes_never_reach_the_ai():
    from box.brain.schemas import Missed
    g = FakeGemini(plan("missed"), Missed(summary="Ravi called and sent you a message."))
    con = FakeConsole()
    assert runner(g, MissedPhone(HOME), con).run("what did I miss").outcome == "done"
    assert con.asked == [] and con.said == ["Ravi called and sent you a message."]
    sent = g.calls[1][1][0]
    assert "Missed call from Ravi Kumar" in sent and "[code]" in sent and "482913" not in sent


def test_louder_says_when_the_phone_was_on_silent():
    class SilentPhone(FakePhone):
        def set_volume(self, level):
            return {"ok": True, "percent": 100, "unsilenced": True}

    con = FakeConsole()
    runner(FakeGemini(plan("volume", [("level", "max")])), SilentPhone(HOME), con).run("my phone doesn't ring")
    assert con.said[-1] == "Your phone was on silent. It will ring again now. The volume is now at 100 percent."
