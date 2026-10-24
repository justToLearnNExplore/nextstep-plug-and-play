"""Shortcuts that do a common task (or its first part) without asking Gemini step by step.

These ask their own, more exact question instead of the plan's (or none):
explain_screen  says what the current screen is and whether it is safe; offers to go back if it isn't
scam_check    "Is this message safe?": fixed rules plus the AI, the more cautious wins; offers only an
              official website (or the cyber-crime portal), never the message's link
missed        "What did I miss?": missed calls, SMS and message notifications of the last hour, read on
              the phone; codes (OTPs) are blanked out on the box before anything goes to the AI
call          looks the person up in the phone's contacts on the box (the list never goes to Gemini), asks
              once naming the exact person and number, then starts the call (Android: CALL intent)
send_message  opens the WhatsApp or SMS chat with the text already typed, asks "Send … to …?", taps Send
battery       reads the level and says it; no question, since nothing changes

These run after the user approved the plan:
set_alarm     Android: the Clock app's own SET_ALARM intent with SKIP_UI, sent by the helper app (which
              holds the permission); without it the box opens the alarm list and the operator finishes
set_timer     same, with SET_TIMER (length in seconds); without the helper it opens the timer screen
play_video    YouTube's own "play from search"; if nothing plays, the operator picks a video
directions    Google Maps with the route drawn (never presses Start)
volume        ring, notification, media and call volume up / down / max (helper app)
web_search / open_link / open_app  jump straight to the right screen; the operator takes it from there
"""

import re
import time
from typing import Any, Callable
from urllib.parse import quote_plus

from ..config import Config
from ..drivers.base import PhoneDriver, ScreenState, center
from ..phrases import phrase
from .safety import link_allowed
from .scam import CYBER_CRIME, RANK, find_by_alias, rule_signals, visible_text
from .schemas import Plan

YOUTUBE = "com.google.android.youtube"
TRAVEL_MODES = {"driving", "walking", "transit", "bicycling", "two-wheeler"}
# "Update your app" / "Update Google Maps to continue": the app won't work until it is updated.
OUTDATED = re.compile(r"\bupdate (your|the) app\b|\bupdate .{1,30} to continue\b|\bout of date\b|"
                      r"\bnew version (is )?available\b", re.I)
SEND_LABEL = re.compile(r"^send( sms| message| mms)?$", re.I)
SEND_IDS = {"send", "send_message_button_container", "send_message_button_icon"}
DURATION = re.compile(r"\b\d+\s*(min|mins|hr|hrs|h)\b", re.I)


def params(plan: Plan) -> dict[str, str]:
    return {p.name: p.value.strip() for p in plan.params}


# ---- contacts --------------------------------------------------------------------------------------

def digits(number: str) -> str:
    return re.sub(r"\D", "", number)


def international(number: str, country_code: str) -> str:
    """The digits WhatsApp wants: country code first, no '+' or leading zeros."""
    n = re.sub(r"[^\d+]", "", number)
    if n.startswith("+"):
        return n[1:]
    if n.startswith("00"):
        return n[2:]
    n = n.lstrip("0")
    return n if len(n) > 10 else country_code + n


def contact_matches(contacts: list[tuple[str, str]], names: list[str], limit: int = 3) -> list[tuple[str, str]]:
    """(name, number) for the person the user named, best first, one entry per number:
    the whole name, then all the words said (e.g. 'Ravi' -> 'Ravi Kumar'), then part of a word."""
    best: dict[str, tuple[int, str, str]] = {}
    for name, number in contacts:
        have = name.casefold().strip()
        words = have.split()
        score = 0
        for said in names:
            want = said.casefold().strip()
            if not want:
                continue
            if have == want:
                score = max(score, 3)
            elif all(w in words for w in want.split()):
                score = max(score, 2)
            elif len(want) >= 3 and want in have:
                score = max(score, 1)
        key = digits(number)
        if score and key and score > best.get(key, (0, "", ""))[0]:
            best[key] = (score, name, number)
    ranked = sorted(best.values(), key=lambda x: (-x[0], x[1].casefold()))
    return [(name, number) for _, name, number in ranked[:limit]]


def people(p: dict[str, str], phone: PhoneDriver) -> list[tuple[str, str]] | None:
    """Who the user means, best first; [] if nobody matches, None if there is nothing to look up."""
    if len(digits(p.get("number", ""))) >= 3:
        return [("", p["number"])]
    names = [p[k] for k in ("contact", "contact_latin") if p.get(k)]
    if not names or not hasattr(phone, "contacts"):
        return None
    contacts = phone.contacts()  # type: ignore[attr-defined]
    return None if contacts is None else contact_matches(contacts, names)


# ---- screens ---------------------------------------------------------------------------------------

def wait_for(phone: PhoneDriver, ok: Callable[[ScreenState], bool], timeout_s: float) -> ScreenState:
    """Looks at the screen until `ok` (or time is up) and returns the last look."""
    deadline = time.monotonic() + timeout_s
    while True:
        screen = phone.capture(False)
        if ok(screen) or time.monotonic() >= deadline:
            return screen
        time.sleep(0.3)


def outdated(screen: ScreenState) -> bool:
    return any(OUTDATED.search(f"{n.get('text', '')} {n.get('desc', '')}") for n in screen.nodes)


def compose_field(screen: ScreenState, text: str) -> dict[str, Any] | None:
    want = " ".join(text.split())
    return next((n for n in screen.nodes if n.get("edit") and want in " ".join(str(n.get("text", "")).split())), None)


def send_button(screen: ScreenState) -> dict[str, Any] | None:
    for n in screen.nodes:
        label = str(n.get("desc") or n.get("text") or "").strip()
        if n.get("click") and (SEND_LABEL.match(label) or n.get("id") in SEND_IDS):
            return n
    return None


def results_loaded(screen: ScreenState, query: str) -> bool:
    """The results are there: the page title ('<query> - Google Search') shows outside the address bar, and
    the page has more than its header (the title comes first, the results a moment later)."""
    want = query.casefold()
    titled = any(want in str(n.get("text") or n.get("desc") or "").casefold() and not n.get("edit") for n in screen.nodes)
    return titled and len(screen.nodes) >= 15


def route_shown(screen: ScreenState) -> bool:
    return "maps" in screen.package and any(DURATION.search(str(n.get("text") or n.get("desc") or "")) for n in screen.nodes)


# ---- before the plan's question ----------------------------------------------------------------------

def before_approval(plan: Plan, phone: PhoneDriver, ui, cfg: Config, brain=None) -> str | None:
    """Playbooks that ask their own, more exact question (or none). Returns the run's outcome,
    'continue' (approved: the operator finishes) or None (not handled: ask the plan's question as usual)."""
    p, lang = params(plan), cfg.language
    if plan.playbook == "explain_screen" and brain is not None:
        return _explain(phone, ui, lang, brain)
    if plan.playbook == "scam_check" and brain is not None:
        return _scam_check(phone, ui, lang, brain)
    if plan.playbook == "missed" and brain is not None and hasattr(phone, "recent_activity"):
        got = phone.recent_activity()  # type: ignore[attr-defined]
        messages = [{**m, "text": hide_codes(str(m.get("text", "")))} for m in got.get("messages", [])]
        ui.say(brain.summarise_missed(got.get("calls", []), messages))
        return "done"
    if plan.playbook == "battery" and hasattr(phone, "battery"):
        b = phone.battery()  # type: ignore[attr-defined]
        if not b.get("ok"):
            return None
        ui.say(phrase(lang, "battery", level=b["level"]) + (f" {phrase(lang, 'charging')}" if b.get("charging") else ""))
        return "done"
    if plan.playbook == "call" and hasattr(phone, "call"):
        return _call(p, phone, ui, lang)
    if plan.playbook == "send_message" and hasattr(phone, "open_chat") and p.get("text"):
        return _send_message(p, phone, ui, cfg)
    return None


CODE = re.compile(r"(?<![₹\d.,/:-])\b\d{4,8}\b(?![.,/:-]?\d)")


def hide_codes(text: str) -> str:
    """OTPs and PINs never leave the phone: 4-8 digit numbers become [code] (amounts with ₹ and phone
    numbers stay)."""
    return CODE.sub("[code]", text)


def _explain(phone: PhoneDriver, ui, lang: str, brain) -> str:
    """Nothing changes, so no question first; a risky screen gets an offer to leave it."""
    exp = brain.explain(phone.capture(True))
    ui.say(exp.explanation)
    if exp.risk != "none" and exp.suggest in ("back", "home"):
        ui.finish_speaking()
        if ui.ask(phrase(lang, "take_back" if exp.suggest == "back" else "go_home_q")):
            phone.execute("go_back" if exp.suggest == "back" else "go_home", {}, None)  # type: ignore[arg-type]
    return "done"


def _scam_check(phone: PhoneDriver, ui, lang: str, brain) -> str:
    text = visible_text(phone.capture(False))
    risk, _, brand = rule_signals(text)
    try:
        verdict = brain.scam_verdict(text)
    except RuntimeError:  # no AI right now: the rules alone still protect
        verdict = None
    if verdict and RANK[verdict.risk] > RANK[risk]:
        risk = verdict.risk
    if risk in ("none", "low"):
        ui.say(phrase(lang, "scam_safe"))
        return "done"
    ui.say((verdict.warning if verdict else "") or phrase(lang, "scam_warning"))
    site = find_by_alias(verdict.impersonates if verdict else "") or find_by_alias(brand) or find_by_alias(text) \
        or CYBER_CRIME
    ui.finish_speaking()
    if ui.ask(phrase(lang, "official_site_q", name=site.name)):
        phone.execute("open_link", {"url": site.url}, None)  # type: ignore[arg-type]
    return "done"


def _not_found(p: dict[str, str], ui, lang: str) -> str:
    ui.say(phrase(lang, "no_contact", name=p.get("contact") or p.get("contact_latin") or p.get("number", "")))
    return "not_found"


def _call(p: dict[str, str], phone: PhoneDriver, ui, lang: str) -> str | None:
    choices = people(p, phone)
    if choices is None:
        return None
    if not choices:
        return _not_found(p, ui, lang)
    for name, number in choices:
        question = (phrase(lang, "call_confirm", name=name, number=number) if name
                    else phrase(lang, "call_number", number=number))
        if not ui.ask(question):
            continue
        res = phone.call(number)  # type: ignore[attr-defined]
        if res.get("ok"):
            ui.say(phrase(lang, "calling", name=name or number))
            return "done"
        if res.get("dialer"):  # e.g. emergency numbers: Android only lets the user press call
            ui.say(phrase(lang, "dial_ready"))
            return "handed_over"
        ui.say(phrase(lang, "not_finished"))
        return "not_possible"
    ui.say(phrase(lang, "declined"))
    return "declined"


def _send_message(p: dict[str, str], phone: PhoneDriver, ui, cfg: Config) -> str | None:
    lang, text = cfg.language, " ".join(p["text"].split())
    choices = people(p, phone)
    if choices is None:
        return None
    if not choices:
        return _not_found(p, ui, lang)
    person = choices[0] if len(choices) == 1 else next(
        (c for c in choices if ui.ask(phrase(lang, "which", name=c[0]))), None)
    if person is None:
        ui.say(phrase(lang, "declined"))
        return "declined"
    name, number = person
    app = p.get("app", "whatsapp").lower()
    opened = phone.open_chat(app, international(number, cfg.country_code), text)  # type: ignore[attr-defined]
    if not opened.get("ok"):
        return None
    screen = wait_for(phone, lambda s: compose_field(s, text) is not None and send_button(s) is not None, 8)
    send = send_button(screen)
    if compose_field(screen, text) is None or send is None:
        return None  # the chat looks different: the operator finishes, and its Send tap asks first
    used = "WhatsApp" if opened.get("app") == "whatsapp" else "SMS"
    if not ui.ask(phrase(lang, "send_confirm", text=text, name=name or number, app=used)):
        ui.say(phrase(lang, "stopped"))
        return "declined_step"
    x, y = center(send, screen)
    phone.execute("click", {"x": x, "y": y}, screen)
    if compose_field(wait_for(phone, lambda s: compose_field(s, text) is None, 3), text) is None:
        ui.say(phrase(lang, "sent", name=name or number))  # the text left the typing box: it went
        return "done"
    return "continue"


# ---- after the plan's question -------------------------------------------------------------------------

def run_playbook(plan: Plan, phone: PhoneDriver, lang: str = "en-IN") -> tuple[str, dict[str, Any]]:
    """('done' | 'continue' | 'skipped' | 'stop', driver result). 'continue' = the operator finishes the task;
    'stop' = the box can't go on (result has 'say' and 'outcome'). A 'say' in the result replaces the plan's
    done message."""
    p = params(plan)
    if plan.playbook == "set_alarm" and hasattr(phone, "set_alarm"):
        try:
            hour, minute = int(p.get("hour", "")), int(p.get("minute", "0") or 0)
        except ValueError:
            return "skipped", {"ok": False, "error": "bad_time"}
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            return "skipped", {"ok": False, "error": "bad_time"}
        res = phone.set_alarm(hour, minute, p.get("label", ""))  # type: ignore[attr-defined]
        if res.get("ok"):
            return "done", res
        return ("continue" if res.get("opened") else "skipped"), res
    if plan.playbook == "set_timer" and hasattr(phone, "set_timer"):
        try:
            seconds = int(float(p.get("seconds", "")))
        except ValueError:
            return "skipped", {"ok": False, "error": "bad_length"}
        if not 1 <= seconds <= 24 * 3600:
            return "skipped", {"ok": False, "error": "bad_length"}
        res = phone.set_timer(seconds, p.get("label", ""))  # type: ignore[attr-defined]
        if res.get("ok"):
            return "done", res
        return ("continue" if res.get("opened") else "skipped"), res
    if plan.playbook == "volume" and hasattr(phone, "set_volume") and p.get("level", "").lower() in ("up", "down", "max"):
        res = phone.set_volume(p["level"].lower())  # type: ignore[attr-defined]
        if res.get("ok") and "percent" in res:
            res["say"] = (phrase(lang, "ringer_on") + " " if res.get("unsilenced") else "") + \
                phrase(lang, "volume", percent=res["percent"])
        return ("done" if res.get("ok") else "skipped"), res
    if plan.playbook == "play_video" and p.get("query"):
        if hasattr(phone, "play_video") and phone.play_video(p["query"]).get("ok"):  # type: ignore[attr-defined]
            playing = lambda: phone.media_playing(YOUTUBE)  # type: ignore[attr-defined]  # noqa: E731
            screen = wait_for(phone, lambda s: outdated(s) or playing(), 10)
            if outdated(screen):
                return "stop", {"ok": False, "outcome": "app_outdated", "say": phrase(lang, "outdated", app="YouTube")}
            return ("done" if playing() else "continue"), {"ok": True}
        url = f"https://www.youtube.com/results?search_query={quote_plus(p['query'])}"
        return "continue", phone.execute("open_link", {"url": url}, None)  # type: ignore[arg-type]
    if plan.playbook == "directions" and p.get("place"):
        mode = p.get("mode", "").lower()
        url = (f"https://www.google.com/maps/dir/?api=1&destination={quote_plus(p['place'])}"
               f"&travelmode={mode if mode in TRAVEL_MODES else 'driving'}")
        res = phone.execute("open_link", {"url": url}, None)  # type: ignore[arg-type]
        screen = wait_for(phone, lambda s: outdated(s) or route_shown(s), 8)
        if outdated(screen):
            return "stop", {"ok": False, "outcome": "app_outdated", "say": phrase(lang, "outdated", app="Google Maps")}
        return ("done" if route_shown(screen) else "continue"), res
    if plan.playbook == "web_search" and p.get("query"):
        url = f"https://www.google.com/search?q={quote_plus(p['query'])}"
        res = phone.execute("open_link", {"url": url}, None)  # type: ignore[arg-type]
        wait_for(phone, lambda s: results_loaded(s, p["query"]), 8)  # else the operator sees an empty page
        return "continue", res
    if plan.playbook == "open_link" and link_allowed(p.get("url", "")):
        return "continue", phone.execute("open_link", {"url": p["url"]}, None)  # type: ignore[arg-type]
    if plan.playbook == "open_app" and (p.get("app") or plan.app):
        res = phone.execute("open_app", {"app_name": p.get("app") or plan.app}, None)  # type: ignore[arg-type]
        return ("continue" if res.get("ok") else "skipped"), res
    return "skipped", {"ok": False, "error": "no_playbook"}
