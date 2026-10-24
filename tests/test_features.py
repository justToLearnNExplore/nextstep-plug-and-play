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
