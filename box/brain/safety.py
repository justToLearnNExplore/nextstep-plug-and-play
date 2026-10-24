"""The box's own safety gates. Every action passes here before it touches the phone.

auto     routine step inside the approved plan: just do it
confirm  irreversible (order, pay, send, call, book, delete, install) or consent (terms, permissions): ask first
private  passwords, PINs, OTPs, payment apps: the user does it themselves, the box never sees it
blocked  never allowed (links outside the allowlist)
"""

import re
from typing import Any

from ..drivers.base import ScreenState
from ..phrases import phrase
from .schemas import Action

IRREVERSIBLE = re.compile(
    r"place order|confirm order|order now|\bpay\b|proceed to pay|make payment|\bsend\b|\bshare\b|install|uninstall|"
    r"delete|remove account|transfer|buy now|submit|add address|save address|request (uber|ride|auto|moto|go)|"
    r"book (now|ride|auto)|confirm (pickup|booking|ride)|cancel (ride|trip)|भेजें|भेजो|ऑर्डर करें|भुगतान|ಕಳುಹಿಸಿ|ಪಾವತಿ|"
    # phoning someone (not opening the call log or the dial pad)
    r"(?<!end )(?<!hold )\bcall\b(?!\s*(log|history|settings|forwarding|waiting|blocking))|\bdial\b(?!\s*pad)|कॉल करें|ಕರೆ ಮಾಡಿ|"
    # agreeing to terms and granting permissions are the user's call too
    r"\baccept\b|\bagree\b|\ballow\b|while using the app|only this time|स्वीकार|अनुमति|ಒಪ್ಪಿ|ಅನುಮತಿಸಿ",
    re.I,
)
SECRET = re.compile(r"password|passcode|\bpin\b|otp|one.?time|cvv|card number|upi|mpin|पासवर्ड|ओटीपी|ಪಾಸ್‌ವರ್ಡ್", re.I)
KEYPAD_EDIT = re.compile(r"^(delete|backspace|del|clear|erase)\b", re.I)
PAYMENT_APPS = {"net.one97.paytm", "com.phonepe.app", "com.google.android.apps.nbu.paisa.user", "in.org.npci.upiapp"}
LINK_ALLOWLIST = (
    "https://www.youtube.com/results?search_query=", "https://m.youtube.com/results?search_query=",
    "https://blinkit.com/s/?q=", "https://m.uber.com/ul/?action=setPickup", "https://www.google.com/search?q=",
    "https://www.google.com/maps/search/", "https://www.google.com/maps/dir/?api=1&destination=",
)


def node_text(node: dict[str, Any] | None) -> str:
    if not node:
        return ""
    return " ".join(str(node.get(k, "")) for k in ("text", "desc", "id")).strip()


def keypad_edit_key(node: dict[str, Any] | None, screen: ScreenState) -> bool:
    """Backspace on an on-screen number pad (timer, dialer, calculator): editing, not deleting data."""
    label = str((node or {}).get("text") or (node or {}).get("desc") or "")
    digits = sum(1 for n in screen.nodes if n.get("click") and len(str(n.get("text") or n.get("desc") or "").strip()) == 1
                 and str(n.get("text") or n.get("desc")).strip().isdigit())
    return digits >= 8 and bool(KEYPAD_EDIT.match(label))


def link_allowed(url: str) -> bool:
    return url.startswith(LINK_ALLOWLIST)


def gate(action: Action, node: dict[str, Any] | None, screen: ScreenState, lang: str) -> tuple[str, str]:
    """(gate, what to say). `node` is the element the box resolved as the target, if any.
    Only ever stricter than the model: its `irreversible` flag can add a question, never remove one."""
    if action.kind == "hand_over":
        return "private", action.intent or phrase(lang, "private")
    if screen.package in PAYMENT_APPS:
        return "private", phrase(lang, "payment")
    if action.kind == "open_link" and not link_allowed(action.text):
        return "blocked", phrase(lang, "blocked")
    label = f"{node_text(node)} {action.label}"
    if action.kind == "type":
        focused = node if node and node.get("edit") else next((n for n in screen.nodes if n.get("focus") and n.get("edit")), None)
        if (focused and (focused.get("secure") or SECRET.search(f"{label} {node_text(focused)}"))) \
                or (screen.has_secure_field and action.text.strip().isdigit()):
            return "private", phrase(lang, "private")
    if action.kind in ("tap", "long_press"):
        if node and node.get("secure"):
            return "private", phrase(lang, "private")
        if action.irreversible or ((IRREVERSIBLE.search(label) or IRREVERSIBLE.search(action.intent))
                                   and not keypad_edit_key(node, screen)):
            return "confirm", f"{action.intent} {phrase(lang, 'confirm')}".strip()
    return "auto", ""
