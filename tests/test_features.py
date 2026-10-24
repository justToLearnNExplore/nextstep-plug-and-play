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


def test_scam_rules_from_nextstep():
    from box.brain.scam import is_lookalike, is_official_domain, rule_signals
    risk, reasons, brand = rule_signals("Dear customer your SBI account is blocked. Update KYC at sbi-kyc-update.in today")
    assert risk == "high" and brand == "State Bank of India" and any(r.startswith("lookalike_domain") for r in reasons)
    assert rule_signals("India Post: your parcel is on hold. Pay Rs 25 redelivery fee immediately http://ind-post.top/pay")[0] == "high"
    assert rule_signals("Amma I will come home by 7, keep dinner ready") == ("none", [], None)
    assert is_official_domain("www.onlinesbi.sbi") and not is_official_domain("incometax-refund.in")
    assert is_official_domain("onlinesbi.sbi.bank.in") and is_official_domain("epfindia.gov.in")
    assert is_lookalike("sbi-bank.in") is not None  # not under .bank.in: a look-alike
    assert is_lookalike("hdfcbank-secure.co") is not None and is_lookalike("hdfcbank.com") is None


SCAM_SMS = screen(node("56767"), node("SBI Alert: Your KYC has expired and your account will be BLOCKED today. "
                                      "Update now at http://sbi-kyc-update.in/verify"), node("Text message", edit=True),
                  package="com.google.android.apps.messaging")


def test_a_scam_gets_a_warning_and_only_the_real_bank_site_is_offered():
    from box.brain.schemas import ScamVerdict
    g = FakeGemini(plan("scam_check"), ScamVerdict(risk="high", reasons=["fake_kyc"], impersonates="SBI",
                                                    warning="This is a fake SBI message. Do not open the link."))
    phone = FakePhone(SCAM_SMS)
    con = FakeConsole(answers=[True])
    assert runner(g, phone, con).run("is this message real?").outcome == "done"
    assert con.said[0] == "This is a fake SBI message. Do not open the link."
    assert con.asked == ["Shall I open the official State Bank of India website?"]
    assert phone.done == [("open_link", {"url": "https://www.onlinesbi.sbi"})]


def test_the_rules_alone_catch_a_scam_the_ai_misses():
    from box.brain.schemas import ScamVerdict
    g = FakeGemini(plan("scam_check"), ScamVerdict(risk="none", reasons=[], impersonates="", warning=""))
    con = FakeConsole(answers=[False])
    runner(g, FakePhone(SCAM_SMS), con).run("is this ok")
    assert "looks like a scam" in con.said[0]


def test_a_family_message_is_called_safe():
    from box.brain.schemas import ScamVerdict
    chat = screen(node("Amma I will come home by 7, keep dinner ready"), package="com.whatsapp")
    g = FakeGemini(plan("scam_check"), ScamVerdict(risk="none", reasons=[], impersonates="", warning=""))
    con = FakeConsole()
    runner(g, FakePhone(chat), con).run("is this safe")
    assert con.said == ["I don't see signs of a scam here. Still, never share your OTP, PIN or password with anyone."]


def test_links_inside_messages_are_never_tapped_unless_official():
    from test_brain import act

    from box.brain.safety import gate
    link = SCAM_SMS.nodes[1]
    assert gate(act("tap", 1, "http://sbi-kyc-update.in/verify"), link, SCAM_SMS, "en-IN")[0] == "blocked"
    real = screen(node("Login at https://www.onlinesbi.sbi", click=True), package="com.google.android.apps.messaging")
    assert gate(act("tap", 0, "Login at https://www.onlinesbi.sbi"), real.nodes[0], real, "en-IN")[0] == "auto"
