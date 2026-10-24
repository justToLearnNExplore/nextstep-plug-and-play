"""The box's agent loop. Its brain is Gemini, called from the box itself (no NextStep server).

plan once → the user says yes once → a playbook if one fits → otherwise: see → decide a few
actions → act. After each action the box re-reads the screen and checks the text the brain said
it would see (`expect`); Gemini is asked again only when the batch is used up or something
unexpected happened. Every step is timed so speed work can be measured.
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .brain.brain import Brain, screen_text
from .brain.playbooks import before_approval, run_playbook
from .brain.safety import gate, node_text, payment_screen
from .brain.schemas import Action, Plan
from .config import Config
from .console import Console
from .drivers.base import PhoneDriver, ScreenState, center
from .phrases import phrase

NEEDS_TARGET = {"tap", "long_press"}


@dataclass
class StepTiming:
    capture_ms: int = 0
    think_ms: int = 0
    act_ms: int = 0
    actions: int = 0
    checked: int = 0  # actions whose result the box verified itself, without asking Gemini
    screenshot: bool = False

    @property
    def total_ms(self) -> int:
        return self.capture_ms + self.think_ms + self.act_ms


@dataclass
class RunReport:
    goal: str
    plan_ms: int = 0
    playbook: str = ""
    steps: list[StepTiming] = field(default_factory=list)
    outcome: str = ""
    started: float = field(default_factory=time.perf_counter)
    wall_s: float = 0.0

    def summary(self) -> str:
        actions = sum(s.actions for s in self.steps)
        head = f"{self.wall_s:.1f} s total, plan {self.plan_ms} ms"
        if self.playbook:
            head += f", playbook {self.playbook}"
        if not self.steps:
            return f"{head} · outcome: {self.outcome}"
        n = len(self.steps)
        avg = lambda f: sum(f(s) for s in self.steps) // n  # noqa: E731
        return (f"{head} · {n} brain turns, {actions} actions ({sum(s.checked for s in self.steps)} checked on the box) · "
                f"per turn: see {avg(lambda s: s.capture_ms)} ms, think {avg(lambda s: s.think_ms)} ms, "
                f"act {avg(lambda s: s.act_ms)} ms · outcome: {self.outcome}")


def timed(fn, *args, **kw):
    t0 = time.perf_counter()
    out = fn(*args, **kw)
    return out, int((time.perf_counter() - t0) * 1000)


def find_by_label(screen: ScreenState, label: str, near: tuple[int, int] | None = None) -> dict[str, Any] | None:
    """The element showing `label`: exact text first, then partial; the one nearest `near` wins."""
    want = label.strip().lower()
    if not want:
        return None
    keys = [(n, [str(n.get(k, "")).strip().lower() for k in ("text", "desc", "id")]) for n in screen.nodes]
    hits = [n for n, ks in keys if want in ks] or \
           [n for n, ks in keys if len(want) >= 3 and any(want in k or (len(k) >= 3 and k in want) for k in ks if k)]
    if not hits:
        return None
    if near is None:
        return hits[0]
    return min(hits, key=lambda n: sum((a - b) ** 2 for a, b in zip(center(n, screen), near)))


def visible(text: str, screen: ScreenState) -> bool:
    want = text.strip().lower()
    return any(want in f"{n.get('text', '')} {n.get('desc', '')}".lower() for n in screen.nodes)


def screen_sig(screen: ScreenState) -> str:
    """Identifies what the screen shows (texts and focus), to notice when an action changed nothing."""
    return hashlib.md5("|".join(f"{node_text(n)}{'*' if n.get('focus') else ''}" for n in screen.nodes)
                       .encode()).hexdigest()[:12]


def label_of(node: dict[str, Any]) -> str:
    return str(node.get("text") or node.get("desc") or node.get("id") or "")


def what_changed(before: ScreenState, after: ScreenState) -> str:
    old = {label_of(n) for n in before.nodes}
    new = list(dict.fromkeys(label_of(n) for n in after.nodes if label_of(n) and label_of(n) not in old))
    return f"New on screen: {', '.join(repr(x[:40]) for x in new[:6])}." if new else "Nothing new appeared."


class Runner:
    def __init__(self, cfg: Config, brain: Brain, phone: PhoneDriver, console: Console, trace: bool = True):
        self.cfg, self.brain, self.phone, self.ui = cfg, brain, phone, console
        self.lang = cfg.language
        self.trace_path: Path | None = None
        if trace:
            runs = Path(cfg.state_dir) / "runs"
            runs.mkdir(parents=True, exist_ok=True)
            self.trace_path = runs / f"{time.strftime('%Y%m%d-%H%M%S')}.jsonl"

    def _trace(self, event: str, **data: Any) -> None:
        """One JSON line per event in ~/.nextstep-box/runs/: stays on the box, for debugging."""
        if self.trace_path:
            with self.trace_path.open("a") as f:
                f.write(json.dumps({"t": round(time.time(), 3), "event": event, **data}, ensure_ascii=False) + "\n")

    def run(self, goal: str = "", speech_wav_b64: str | None = None) -> RunReport:
        """Does what was asked: typed (`goal`) or spoken (a recording, heard by the brain itself)."""
        report = RunReport(goal=goal)
        try:
            report.outcome = self._run(goal, report, speech_wav_b64)
        finally:
            report.wall_s = time.perf_counter() - report.started
        return report

    def _awake(self) -> bool:
        """Wakes the phone; if a PIN lock is showing, the user unlocks it. False = they said stop."""
        if not hasattr(self.phone, "wake") or not self.phone.wake().get("locked"):  # type: ignore[attr-defined]
            return True
        if self.ui.ask(phrase(self.lang, "unlock"), yes="Done", no="Stop"):
            return True
        self.ui.say(phrase(self.lang, "stopped"))
        return False

    def _run(self, goal: str, report: RunReport, speech_wav_b64: str | None = None) -> str:
        self.ui.status(phrase(self.lang, "thinking"))
        if not self._awake():
            return "stopped_by_user"
        screen = self.phone.capture(False)
        try:
            plan, report.plan_ms = timed(self.brain.plan, goal, screen, speech_wav_b64)
        except RuntimeError as e:
            self.ui.status(f"({str(e)[:200]})")
            self.ui.say(phrase(self.lang, "no_brain"))
            return "plan_failed"
        self._trace("plan", goal=goal, spoken=bool(speech_wav_b64), ms=report.plan_ms, plan=plan.model_dump())
        if speech_wav_b64:
            report.goal = plan.heard
            if not plan.goal.strip():  # nothing that asks for something: noise, TV, people talking
                self.ui.say(phrase(self.lang, "not_understood"))
                return "not_understood"
            self.ui.status(f"🎤 {plan.heard}")
        if plan.refused:
            self.ui.say(plan.summary)
            return "refused"
        # Calls, messages and the battery ask their own, more exact question (or none).
        outcome = before_approval(plan, self.phone, self.ui, self.cfg)
        if outcome:
            report.playbook = plan.playbook
            self._trace("playbook", name=plan.playbook, outcome=outcome)
            return self._operate(plan, report) if outcome == "continue" else outcome
        if not self.ui.ask(plan.summary, details=plan.steps, plan=True):
            self.ui.say(phrase(self.lang, "declined"))
            return "declined"

        if plan.playbook != "none":
            status, res = run_playbook(plan, self.phone, self.lang)
            self._trace("playbook", name=plan.playbook, status=status, result=res)
            if status != "skipped":
                report.playbook = plan.playbook
            if status == "done":
                self.ui.say(res.get("say") or plan.done_message or phrase(self.lang, "done"))
                return "done"
            if status == "stop":
                self.ui.say(res["say"])
                return res["outcome"]
        return self._operate(plan, report)

    # ---- see → decide → act -------------------------------------------------------------------

    def _operate(self, plan: Plan, report: RunReport) -> str:
        history: list[str] = []
        no_effect: dict[str, int] = {}
        visits: dict[str, int] = {}
        note, think_hard, screen = "", False, None
        want_image = True  # the first look includes a screenshot; later ones only when needed
        for _ in range(self.cfg.max_turns):
            t = StepTiming()
            if not self._awake():  # the screen may have timed out while the brain was thinking
                return "stopped_by_user"
            if screen is None or (want_image and not screen.screenshot_b64):
                screen, t.capture_ms = timed(self.phone.capture, want_image)
            if payment_screen(screen):
                # Never show a payment app to the AI: the user finishes it.
                if not self.ui.ask(phrase(self.lang, "payment"), yes="Done", no="Stop"):
                    self.ui.say(phrase(self.lang, "stopped"))
                    return "stopped_by_user"
                history.append("the user finished a payment app step themselves")
                screen = None
                continue
            if len(screen.nodes) < 5 and not screen.screenshot_b64:  # little to read: look at the pixels
                screen, ms = timed(self.phone.capture, True)
                t.capture_ms += ms
            with_image = bool(screen.screenshot_b64) and not screen.has_secure_field
            sig = screen_sig(screen)
            visits[sig] = visits.get(sig, 0) + 1
            if visits[sig] > 6:  # going round in circles
                self.ui.say(phrase(self.lang, "stuck"))
                return "stuck"
            try:
                turn, t.think_ms = timed(self.brain.next_turn, plan, history, screen, note, with_image, think_hard)
                if turn.need_screenshot and not with_image and not screen.has_secure_field:
                    screen, ms = timed(self.phone.capture, True)
                    t.capture_ms += ms
                    turn, ms = timed(self.brain.next_turn, plan, history, screen, note, True, think_hard)
                    t.think_ms += ms
                    with_image = True
            except RuntimeError as e:
                self.ui.status(f"({str(e)[:200]})")
                self.ui.say(phrase(self.lang, "no_brain"))
                return "brain_failed"
            t.screenshot = with_image
            self._trace("turn", ms=t.think_ms, note=note, image=with_image, screen=screen_text(screen), turn=turn.model_dump())
            if turn.done:
                report.steps.append(t)
                self.ui.timing(t)
                if turn.success:
                    self.ui.say(turn.message or plan.done_message or phrase(self.lang, "done"))
                    return "done"
                self.ui.say(turn.message or phrase(self.lang, "not_finished"))
                return "not_possible"

            screen, note, ending, think_hard = self._run_batch(turn.actions, screen, history, no_effect, t)
            want_image = bool(note)  # something unexpected: let the brain see the screen next time
            report.steps.append(t)
            self.ui.timing(t)
            if ending:
                return ending
        self.ui.say(phrase(self.lang, "too_long"))
        return "too_long"

    def _run_batch(self, actions: list[Action], screen: ScreenState, history: list[str],
                   no_effect: dict[str, int], t: StepTiming) -> tuple[ScreenState | None, str, str, bool]:
        """Runs the brain's actions in order, checking each one on the box.
        Returns (latest screen or None, note for the brain, outcome if the task must end, think hard)."""
        first_screen = screen
        if not actions:
            return None, "You returned no actions. Choose the next action, or set done.", "", False
        for i, a in enumerate(actions[:5]):
            node, xy = self._resolve(a, screen, first_screen, first=(i == 0))
            if a.kind in NEEDS_TARGET and xy is None:
                return screen, f"Could not find '{a.label}' on the screen. Look again.", "", False

            g, prompt = gate(a, node, screen, self.lang)
            if g == "blocked":
                self.ui.say(prompt)
                return screen, "That link is not allowed. Do it inside the app instead.", "", False
            if g == "private":
                if not self.ui.ask(prompt, yes="Done", no="Stop"):
                    self.ui.say(phrase(self.lang, "stopped"))
                    return None, "", "stopped_by_user", False
                history.append(f"the user did a private step themselves ({a.intent})")
                return None, "", "", False
            if g == "confirm" and not self.ui.ask(prompt):
                self.ui.say(phrase(self.lang, "stopped"))
                return None, "", "declined_step", False
            if a.intent:
                self.ui.status(a.intent, speak=a.announce and g == "auto")

            result, ms = timed(self._act, a, node, xy, screen)
            self._trace("act", kind=a.kind, label=a.label, text=a.text, xy=xy, gate=g, result=result, ms=ms)
            t.act_ms += ms
            t.actions += 1
            history.append(f"{a.intent or a.kind}" + ("" if result.get("ok") else f" -> FAILED ({result.get('error')})"))
            if not result.get("ok"):
                return None, f"'{a.intent or a.kind}' failed: {result.get('error')}. Try another way.", "", False

            before = screen
            screen, ms = timed(self.phone.capture, False)
            t.capture_ms += ms
            rest = " The rest of your actions were skipped." if i < len(actions) - 1 else ""
            if a.kind in ("tap", "long_press", "type") and screen_sig(screen) == screen_sig(before):
                key = f"{screen_sig(before)}:{a.kind}:{a.label}:{a.text}"
                no_effect[key] = no_effect.get(key, 0) + 1
                if no_effect[key] >= 3:
                    self.ui.say(phrase(self.lang, "stuck"))
                    return None, "", "stuck", False
                return screen, (f"'{a.intent or a.kind}' changed nothing on the screen.{rest} Try something else "
                                "(another element, scroll, or back)."), "", no_effect[key] >= 2
            if a.expect:
                if not visible(a.expect, screen):
                    return screen, (f"After '{a.intent or a.kind}', '{a.expect}' is not on the screen. "
                                    f"{what_changed(before, screen)}{rest}"), "", False
                t.checked += 1
            if g == "confirm":
                break  # always look again after an irreversible step
        return screen, "", "", False

    def _resolve(self, a: Action, screen: ScreenState, first_screen: ScreenState,
                 first: bool) -> tuple[dict[str, Any] | None, tuple[int, int] | None]:
        """The target element and its 0-999 centre. The index is only trusted on the screen the
        brain saw; later actions in a batch find their element again by its label."""
        indexed = first_screen.nodes[a.element] if 0 <= a.element < len(first_screen.nodes) else None
        if first and indexed is not None:
            if not a.label or a.label.lower() in node_text(indexed).lower() or node_text(indexed).lower() in a.label.lower():
                return indexed, center(indexed, screen)
        label = a.label or node_text(indexed)
        near = center(indexed, first_screen) if indexed is not None else None
        if node := find_by_label(screen, label, near):
            return node, center(node, screen)
        if first and indexed is not None:
            return indexed, center(indexed, screen)  # label differs, but the index is from this very screen
        if a.x >= 0 and a.y >= 0:
            return None, (a.x, a.y)
        return None, None

    def _act(self, a: Action, node: dict[str, Any] | None, xy: tuple[int, int] | None,
             screen: ScreenState) -> dict[str, Any]:
        run = self.phone.execute
        if a.kind == "tap":
            return run("click", {"x": xy[0], "y": xy[1]}, screen)  # type: ignore[index]
        if a.kind == "long_press":
            return run("long_press", {"x": xy[0], "y": xy[1]}, screen)  # type: ignore[index]
        if a.kind == "type":
            if node and node.get("edit") and not node.get("focus") and xy:
                res = run("click", {"x": xy[0], "y": xy[1]}, screen)
                if not res.get("ok"):
                    return res
            return run("type", {"text": a.text, "press_enter": a.press_enter}, screen)
        if a.kind == "scroll":
            if node and node.get("scroll"):
                b = node["b"]
                x = center(node, screen)[0]
                top, bottom = int(b[1] * 1000 / screen.height), int(b[3] * 1000 / screen.height)
            else:
                x, top, bottom = 500, 150, 850
            span = bottom - top
            lo, hi = top + span // 5, bottom - span // 5
            start, end = (hi, lo) if a.direction != "up" else (lo, hi)
            return run("drag_and_drop", {"start_x": x, "start_y": start, "end_x": x, "end_y": end}, screen)
        if a.kind == "back":
            return run("go_back", {}, screen)
        if a.kind == "home":
            return run("go_home", {}, screen)
        if a.kind == "open_app":
            return run("open_app", {"app_name": a.text}, screen)
        if a.kind == "open_link":
            return run("open_link", {"url": a.text}, screen)
        if a.kind == "wait":
            return run("wait", {"seconds": 2}, screen)
        return {"ok": False, "error": f"unsupported:{a.kind}"}
