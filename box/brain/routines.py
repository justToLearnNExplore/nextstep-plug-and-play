"""Learned routines: a step-by-step task that worked becomes a recipe the box replays next time with
almost no AI (rebuilt from NextStep's learned skills).

A recipe keeps each step by the *name* of what was tapped ("tap 'Search'", "type {item}", "tap 'ADD'
next to '{item} 1 L'"), never screen positions, and the task's details become slots, so "order
bread" reuses what "order milk" learned. Replay matches names on the live screen; the first step that
doesn't match hands over to the AI, which also checks the result. Every replayed step goes through
the safety gates, so "Place order" always asks. Recipes stay on the box (~/.nextstep-box/routines.json).
"""

import json
import re
import time
from pathlib import Path
from typing import Any

from ..drivers.base import ScreenState

REPLAYABLE = {"tap", "long_press", "type", "scroll", "back", "home", "open_app", "wait"}
MIN_MATCH = 0.6
GENERIC = re.compile(r"^(add|\+|buy|ok|go|next|select|open|view|more|यहाँ|जोड़ें|ಸೇರಿಸಿ)$", re.I)
UNITS = {"litre", "liter", "litres", "kg", "gram", "grams", "ml", "pack", "packet", "one", "two", "half"}


def label_of(n: dict[str, Any]) -> str:
    return str(n.get("text") or n.get("desc") or "").strip()


def tokens(s: str) -> set[str]:
    return {t for t in re.findall(r"[\w₹]+", s.lower()) if len(t) > 1 or t.isdigit()}


def similarity(a: str, b: str) -> float:
    ta, tb = tokens(a), tokens(b)
    if not ta or not tb:
        return 0.0
    if a.strip().lower() == b.strip().lower():
        return 1.0
    return len(ta & tb) / len(ta | tb) * 0.7 + (0.3 if (a.lower() in b.lower() or b.lower() in a.lower()) else 0.0)


def templatize(text: str, params: dict[str, str]) -> str:
    """'Amul Taaza milk 1 L' with item='milk 1 litre' -> 'Amul Taaza {item} 1 L': the whole value first,
    then its most distinctive word (product titles rarely match word for word)."""
    for k, v in sorted(params.items(), key=lambda kv: -len(kv[1])):
        if not v or len(v) < 2:
            continue
        new = re.sub(re.escape(v), "{" + k + "}", text, flags=re.I)
        if new == text:
            for word in sorted(tokens(v), key=len, reverse=True):
                if len(word) >= 3 and not word.isdigit() and word not in UNITS:
                    new = re.sub(rf"(?<!\w){re.escape(word)}(?!\w)", "{" + k + "}", text, count=1, flags=re.I)
                    if new != text:
                        break
        text = new
    return text


def fill(text: str, params: dict[str, str]) -> str:
    return re.sub(r"\{(\w+)\}", lambda m: params.get(m.group(1), m.group(0)), text)


def middle(n: dict[str, Any]) -> tuple[float, float]:
    """An element's centre in pixels (distances must not stretch across and down differently)."""
    b = n["b"]
    return (b[0] + b[2]) / 2, (b[1] + b[3]) / 2


def context_of(screen: ScreenState, node: dict[str, Any]) -> str:
    """For generic buttons ('ADD', '+'), the nearest descriptive text (the product above it). A button with
    a name of its own ('Display') needs none."""
    if not GENERIC.match(label_of(node)) and len(label_of(node)) > 3:
        return ""
    cx, cy = middle(node)
    best, best_d = "", float("inf")
    for n in screen.nodes:
        lbl = label_of(n)
        if n is node or not lbl or n.get("secure") or GENERIC.match(lbl) or len(lbl) < 4:
            continue
        x, y = middle(n)
        d = ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5
        if d < best_d and abs(y - cy) < screen.height * 0.2:  # roughly the same card
            best, best_d = lbl, d
    return best[:80]


def step_from(kind: str, node: dict[str, Any] | None, text: str, direction: str, enter: bool, screen: ScreenState,
              params: dict[str, str]) -> dict[str, Any] | None:
    """An executed action as a position-free recipe step, or None if it can't be replayed by name."""
    if kind not in REPLAYABLE:
        return None
    step: dict[str, Any] = {"kind": kind, "package": screen.package}
    if kind in ("tap", "long_press"):
        if not node or not label_of(node) or node.get("secure"):
            return None  # tapped an unnamed spot: can't be found again by name
        step["label"] = templatize(label_of(node), params)
        if ctx := context_of(screen, node):
            step["context"] = templatize(ctx, params)
    elif kind in ("type", "open_app"):
        step["text"] = templatize(text, params)
        if kind == "type":
            step["enter"] = enter
    elif kind == "scroll":
        step["direction"] = direction
    return step


def details(params: dict[str, str]) -> dict[str, str]:
    """The task's details that vary between runs: the app is part of the routine itself."""
    return {k: v for k, v in params.items() if k != "app"}


def generic_steps(steps: list[dict[str, Any]], params: dict[str, str]) -> list[dict[str, Any]]:
    """Drops steps tied to one particular order (typing a literal product name, or tapping a button that
    belongs to a product that isn't a slot), else 'order bread' would re-add last week's toffees."""
    keep = []
    for s in steps:
        if params and s["kind"] == "type" and "{" not in s.get("text", ""):
            continue
        if params and s["kind"] in ("tap", "long_press") and s.get("context") and "{" not in s["context"]:
            continue
        keep.append(s)
    return keep if any(s["kind"] in ("tap", "long_press", "type") for s in keep) else []


def find(screen: ScreenState, label: str, context: str = "") -> dict[str, Any] | None:
    """The live element for a recipe name; with a remembered context ('Amul Taaza ... 1 L') the candidate
    nearest to matching text, so a lone 'ADD' next to another product is not taken."""
    candidates = [(similarity(label, label_of(n)) + (0.05 if n.get("click") else 0), n)
                  for n in screen.nodes if label_of(n) and not n.get("secure")]
    candidates = [(s, n) for s, n in candidates if s >= MIN_MATCH]
    if not candidates:
        return None
    if context:
        picked = [n for _, n in candidates]
        anchors = [n for n in screen.nodes if label_of(n) and n not in picked and similarity(context, label_of(n)) >= 0.5]
        if not anchors:
            return None  # the item isn't on this screen: let the AI look (scroll, search)

        def dist(n: dict[str, Any]) -> float:  # same row matters most; a title left of its button is still its own
            cx, cy = middle(n)
            return min(abs(cy - middle(a)[1]) + 0.3 * abs(cx - middle(a)[0]) for a in anchors)
        best = min(picked, key=dist)
        return best if dist(best) <= screen.height * 0.12 else None
    return max(candidates, key=lambda sn: sn[0])[1]


class Routines:
    """Recipes on the box, by task kind ('blinkit_add_item')."""

    def __init__(self, path: Path | None):
        self.path = path  # None: kept in memory only (tests)
        try:
            self.data: dict[str, Any] = json.loads(path.read_text()) if path else {}
        except (OSError, ValueError):
            self.data = {}

    def get(self, key: str) -> dict[str, Any] | None:
        r = self.data.get(key)
        return r if r and r["successes"] > r.get("failures", 0) else None

    def learn(self, key: str, params: dict[str, str], trace: list[dict[str, Any]]) -> None:
        """A successful run: keep its recipe (or reinforce a proven, shorter one)."""
        if any(re.search(r"\d$", k) for k in params):
            return  # several items (item, item2...) can't be one recipe
        steps = generic_steps(trace, params)
        old = self.data.get(key)
        if len(steps) < 2:
            return
        if old and len(old["steps"]) <= len(steps) and old["successes"] >= 2:
            old["successes"] += 1
        else:
            self.data[key] = {"steps": steps, "params": sorted(params), "failures": 0,
                              "successes": (old["successes"] + 1) if old else 1}
        self.data[key]["updated_at"] = time.time()
        self._save()

    def failed(self, key: str) -> None:
        if key in self.data:
            self.data[key]["failures"] = self.data[key].get("failures", 0) + 1
            self._save()

    def _save(self) -> None:
        if not self.path:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=1))
