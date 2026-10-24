"""The box's agent loop: plan once, the user says yes once, then see → decide → act until done.

Same protocol and safety model as the NextStep Android app (backend/app on Cloud Run decides; the
box only executes): `auto` runs, `confirm` asks first, `private` hands the step to the user,
`blocked` never runs. Every step is timed so speed work can be measured.
"""

import time
from dataclasses import dataclass, field
from typing import Any

from .backend import Backend, BackendError
from .config import Config
from .console import Console
from .drivers.base import PhoneDriver, ScreenState


@dataclass
class StepTiming:
    capture_ms: int = 0
    server_ms: int = 0
    act_ms: int = 0
    source: str = ""
    actions: int = 0
    screenshot: bool = False

    @property
    def total_ms(self) -> int:
        return self.capture_ms + self.server_ms + self.act_ms


@dataclass
class RunReport:
    goal: str
    plan_ms: int = 0
    steps: list[StepTiming] = field(default_factory=list)
    outcome: str = ""

    def summary(self) -> str:
        if not self.steps:
            return f"plan {self.plan_ms} ms, no steps ({self.outcome})"
        n = len(self.steps)
        avg = lambda f: sum(f(s) for s in self.steps) // n  # noqa: E731
        total = (self.plan_ms + sum(s.total_ms for s in self.steps)) / 1000
        return (f"{n} steps in {total:.1f} s (plan {self.plan_ms} ms) · per step: "
                f"see {avg(lambda s: s.capture_ms)} ms, think {avg(lambda s: s.server_ms)} ms, "
                f"act {avg(lambda s: s.act_ms)} ms · outcome: {self.outcome}")


class Runner:
    def __init__(self, cfg: Config, backend: Backend, phone: PhoneDriver, console: Console):
        self.cfg, self.api, self.phone, self.ui = cfg, backend, phone, console

    def _timed(self, fn, *args):
        t0 = time.perf_counter()
        out = fn(*args)
        return out, int((time.perf_counter() - t0) * 1000)

    def run(self, goal: str) -> RunReport:
        report = RunReport(goal=goal)
        self.api.warm()
        self.ui.status("Let me think about that…")
        screen, _ = self._timed(self.phone.capture, True)
        try:
            res, report.plan_ms = self._timed(self.api.post, "/v1/tasks",
                                              {"goal": goal, "language": self.cfg.language, "screen": screen.to_json()})
        except BackendError as e:
            self.ui.say(f"Sorry, I couldn't plan that ({e.status}).")
            report.outcome = "plan_failed"
            return report
        task_id, plan = res["task_id"], res["plan"]
        if plan.get("refused"):
            self.ui.say(plan.get("summary", "I can't do that."))
            report.outcome = "refused"
            return report
        if plan.get("special_flow"):
            self.ui.say("That needs the camera; the box will do that in a later version.")
            report.outcome = f"unsupported:{plan['special_flow']}"
            return report

        approved = self.ui.ask(plan["summary"], details=plan.get("steps", []))
        self.api.post(f"/v1/tasks/{task_id}/consent", {"approved": approved})
        if not approved:
            self.ui.say("Okay, I won't do it.")
            report.outcome = "declined"
            return report

        results: list[dict[str, Any]] = []
        for _ in range(self.cfg.max_turns):
            t = StepTiming()
            screen, t.capture_ms = self._timed(self.phone.capture, False)
            step, t.server_ms = self._timed(self.api.post, f"/v1/tasks/{task_id}/step",
                                            {"screen": screen.to_json(), "results": results})
            if step.get("need_screenshot"):
                t.screenshot = True
                screen, ms = self._timed(self.phone.capture, True)
                t.capture_ms += ms
                step, ms = self._timed(self.api.post, f"/v1/tasks/{task_id}/step",
                                       {"screen": screen.to_json(), "results": []})
                t.server_ms += ms
            t.source = step.get("source", "")
            if text := step.get("status_text"):
                first = (step.get("actions") or [{}])[0]
                self.ui.status(text, speak=bool(first.get("announce")) and first.get("gate") == "auto")
            if step.get("done"):
                report.steps.append(t)
                if step.get("message"):
                    self.ui.say(step["message"])
                    report.outcome = "done"
                else:
                    # The backend stops silently when the agent loops; never call that a success.
                    self.ui.say("I couldn't finish that. Nothing was ordered or sent.")
                    report.outcome = "stopped"
                return report
            results = []
            t0 = time.perf_counter()
            for a in step.get("actions", []):
                result = self._run_gated(a, screen)
                results.append({"call_id": a.get("call_id", ""), "name": a["name"], "result": result})
                t.actions += 1
                if result.get("error") in ("user_declined", "user_stopped"):
                    break
            t.act_ms = int((time.perf_counter() - t0) * 1000)
            report.steps.append(t)
            self.ui.timing(t)
        self.ui.say("This is taking too long, so I stopped. Nothing was ordered or sent.")
        report.outcome = "too_long"
        return report

    def _run_gated(self, a: dict[str, Any], screen: ScreenState) -> dict[str, Any]:
        gate, name, args = a.get("gate", "confirm"), a["name"], a.get("args") or {}
        prompt = a.get("ask") or a.get("intent") or "Shall I do this?"
        if gate == "blocked":
            self.ui.say(prompt)
            return {"ok": False, "error": "blocked_by_safety"}
        if gate == "private" or name == "hand_over_to_user":
            done = self.ui.ask(prompt, yes="Done", no="Stop")
            return {"ok": True, "handed_to_user": True} if done else {"ok": False, "error": "user_stopped"}
        if gate == "confirm":
            if not self.ui.ask(prompt, yes=a.get("yes_label") or "Yes", no="No"):
                return {"ok": False, "error": "user_declined"}
            result = self.phone.execute(name, args, screen)
            result["safety_acknowledgement"] = True
            return result
        return self.phone.execute(name, args, screen)
