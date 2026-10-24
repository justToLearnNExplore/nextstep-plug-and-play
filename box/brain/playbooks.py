"""Shortcuts that do a common task (or its first part) without asking Gemini step by step.

set_alarm  Android: the Clock app's own SET_ALARM intent with SKIP_UI, sent by the helper app (which
           holds the permission); without it the box opens the alarm list and the operator finishes
set_timer  same, with SET_TIMER (length in seconds); without the helper it opens the timer screen
web_search / open_link / open_app  jump straight to the right screen; the operator takes it from there
"""

from typing import Any
from urllib.parse import quote_plus

from ..drivers.base import PhoneDriver
from .safety import link_allowed
from .schemas import Plan


def params(plan: Plan) -> dict[str, str]:
    return {p.name: p.value for p in plan.params}


def run_playbook(plan: Plan, phone: PhoneDriver) -> tuple[str, dict[str, Any]]:
    """('done' | 'continue' | 'skipped', driver result). 'continue' = the operator finishes the task."""
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
    if plan.playbook == "web_search" and p.get("query"):
        url = f"https://www.google.com/search?q={quote_plus(p['query'])}"
        return "continue", phone.execute("open_link", {"url": url}, None)  # type: ignore[arg-type]
    if plan.playbook == "open_link" and link_allowed(p.get("url", "")):
        return "continue", phone.execute("open_link", {"url": p["url"]}, None)  # type: ignore[arg-type]
    if plan.playbook == "open_app" and (p.get("app") or plan.app):
        res = phone.execute("open_app", {"app_name": p.get("app") or plan.app}, None)  # type: ignore[arg-type]
        return ("continue" if res.get("ok") else "skipped"), res
    return "skipped", {"ok": False, "error": "no_playbook"}
