"""Scam check: fixed rules on the box plus Gemini's judgement, the more cautious of the two wins
(rebuilt from NextStep's scam shield).

The box only ever offers a website from OFFICIAL below, never a link from a message, and it never taps
a link inside a message unless the link is official.
"""

import re
import unicodedata
from dataclasses import dataclass
from urllib.parse import urlparse

from ..drivers.base import ScreenState


@dataclass(frozen=True)
class Official:
    name: str
    url: str
    domains: tuple[str, ...]
    aliases: tuple[str, ...]


OFFICIAL: list[Official] = [
    Official("State Bank of India", "https://www.onlinesbi.sbi", ("sbi.co.in", "onlinesbi.sbi", "sbi"), ("sbi", "state bank")),
    Official("HDFC Bank", "https://www.hdfcbank.com", ("hdfcbank.com",), ("hdfc",)),
    Official("ICICI Bank", "https://www.icicibank.com", ("icicibank.com",), ("icici",)),
    Official("Axis Bank", "https://www.axisbank.com", ("axisbank.com",), ("axis bank",)),
    Official("Canara Bank", "https://canarabank.com", ("canarabank.com", "canarabank.in"), ("canara",)),
    Official("Punjab National Bank", "https://www.pnbindia.in", ("pnbindia.in", "pnb.bank.in"), ("pnb", "punjab national")),
    Official("Bank of Baroda", "https://www.bankofbaroda.in", ("bankofbaroda.in", "bankofbaroda.com"), ("bank of baroda", "bob")),
    Official("India Post", "https://www.indiapost.gov.in", ("indiapost.gov.in",), ("india post", "indiapost", "speed post")),
    Official("Income Tax Department", "https://www.incometax.gov.in", ("incometax.gov.in",), ("income tax", "itr", "refund")),
    Official("UIDAI (Aadhaar)", "https://uidai.gov.in", ("uidai.gov.in",), ("aadhaar", "aadhar", "uidai")),
    Official("EPFO", "https://www.epfindia.gov.in", ("epfindia.gov.in",), ("epfo", "pf", "provident fund")),
    Official("Electricity (BESCOM)", "https://bescom.karnataka.gov.in", ("bescom.karnataka.gov.in", "bescom.co.in"),
             ("bescom", "electricity bill", "power cut")),
    Official("National Cyber Crime Portal", "https://cybercrime.gov.in", ("cybercrime.gov.in",), ("cyber crime", "police")),
    Official("Blinkit", "https://blinkit.com", ("blinkit.com",), ("blinkit",)),
    Official("WhatsApp", "https://www.whatsapp.com", ("whatsapp.com", "wa.me"), ("whatsapp",)),
]
CYBER_CRIME = next(o for o in OFFICIAL if o.url == "https://cybercrime.gov.in")  # where to report fraud in India

URL = re.compile(r"(https?://[^\s]+|\b[\w-]+(?:\.[\w-]+)*\.(?:com|in|net|org|co|xyz|top|info|link|ly|me|site|online|app)"
                 r"\b[^\s]*)", re.I)
URGENCY = re.compile(r"(urgent|immediately|today|tonight|within 24|last chance|blocked|suspend|disconnect|expire|arrest|"
                     r"legal action|तुरंत|आज ही|बंद|ತಕ್ಷಣ|ಇಂದೇ)", re.I)
ASKS_SECRET = re.compile(r"(otp|\bpin\b|cvv|password|upi|kyc|pan card|aadhaar|anydesk|teamviewer|\.apk|ओटीपी|पिन|ಒಟಿಪಿ|ಪಿನ್)",
                         re.I)
MONEY = re.compile(r"(₹|rs\.?|inr|refund|prize|lottery|cashback|reward|won|jeeta|ಬಹುಮಾನ|इनाम)", re.I)
RANK = {"none": 0, "low": 1, "medium": 2, "high": 3}


# Only verified banks can register .bank.in, and only government bodies .gov.in.
TRUSTED_SUFFIXES = (".bank.in", ".gov.in")


def is_official_domain(host: str) -> bool:
    host = host.lower().rstrip(".")
    return host.endswith(TRUSTED_SUFFIXES) or any(host == d or host.endswith("." + d) for o in OFFICIAL for d in o.domains)


def official_url(url: str) -> bool:
    return any(url.rstrip("/") == o.url for o in OFFICIAL)


def find_by_alias(text: str | None) -> Official | None:
    t = (text or "").lower()
    return next((o for o in OFFICIAL if any(re.search(rf"\b{re.escape(a)}\b", t) for a in o.aliases)), None)


def _skeleton(s: str) -> str:
    """Look-alike letters made plain, so 'sbi-kyc-update.in', 'hdfcbank-secure.co' and 'ıcıcı' compare."""
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return s.translate(str.maketrans({"0": "o", "1": "l", "3": "e", "5": "s", "@": "a"})).replace("-", "")


def is_lookalike(host: str) -> Official | None:
    """A domain that names a known brand but isn't one of its official domains."""
    if is_official_domain(host):
        return None
    sk = _skeleton(host)
    for o in OFFICIAL:
        for d in o.domains:
            brand = _skeleton(d.split(".")[0])
            if len(brand) >= 3 and brand in sk:
                return o
    return None


def hosts(text: str) -> list[str]:
    out = []
    for raw in URL.findall(text):
        host = (urlparse(raw if raw.lower().startswith("http") else f"https://{raw}").hostname or "").lower()
        if host:
            out.append(host)
    return out


def rule_signals(text: str) -> tuple[str, list[str], str | None]:
    """(risk none|low|medium|high, reasons, brand it pretends to be) from fixed rules alone."""
    reasons: list[str] = []
    brand = None
    for host in hosts(text):
        if (o := is_lookalike(host)) is not None:
            reasons.append(f"lookalike_domain:{host}")
            brand = o.name
        elif not is_official_domain(host):
            reasons.append(f"unverified_link:{host}")
    if URGENCY.search(text):
        reasons.append("urgency")
    if ASKS_SECRET.search(text):
        reasons.append("asks_sensitive_info")
    if MONEY.search(text):
        reasons.append("money_bait")
    has_link = any(r.startswith(("lookalike", "unverified")) for r in reasons)
    if any(r.startswith("lookalike") for r in reasons) or (has_link and "asks_sensitive_info" in reasons):
        risk = "high"
    elif has_link and ("urgency" in reasons or "money_bait" in reasons):
        risk = "high"
    elif "asks_sensitive_info" in reasons and "urgency" in reasons:
        risk = "medium"
    elif has_link or len(reasons) >= 2:
        risk = "low"
    else:
        risk = "none"
    return risk, reasons, brand


def visible_text(screen: ScreenState, limit: int = 3000) -> str:
    """The screen's words top to bottom, without password fields; the newest messages are at the bottom."""
    seen, lines = set(), []
    for n in sorted((n for n in screen.nodes if not n.get("secure")), key=lambda n: n["b"][1]):
        t = str(n.get("text") or n.get("desc") or "").strip()
        if t and t not in seen:
            seen.add(t)
            lines.append(t)
    return "\n".join(lines)[-limit:]


def unsafe_link(label: str) -> bool:
    """A link shown in a message that isn't an official site: the box never opens it."""
    return any(not is_official_domain(h) for h in hosts(label))
