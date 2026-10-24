"""The direct Gemini client's fallbacks, with a fake Google client (no network)."""

from types import SimpleNamespace

import httpx
import pytest
from google.genai import errors
from pydantic import BaseModel

from box.brain import gemini as gemini_mod
from box.brain.gemini import Gemini


class Answer(BaseModel):
    text: str


def ok(text="hi"):
    return SimpleNamespace(parsed=Answer(text=text), usage_metadata=None)


def api_error(code):
    return errors.APIError(code, {"error": {"code": code, "message": "x", "status": "X"}})


class FakeModels:
    """Each model name maps to a list of outcomes (an exception to raise, or a response), used in order."""

    def __init__(self, script):
        self.script = {m: list(v) for m, v in script.items()}
        self.tried: list[str] = []

    def generate_content(self, model, contents, config):
        self.tried.append(model)
        out = self.script[model].pop(0)
        if isinstance(out, Exception):
            raise out
        return out


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(gemini_mod.time, "sleep", lambda s: None)


def client(script) -> tuple[Gemini, FakeModels]:
    g = Gemini.__new__(Gemini)
    g.calls = g.input_tokens = g.output_tokens = 0
    g.gone, g.resting = set(), {}
    fake = FakeModels(script)
    g.client = SimpleNamespace(models=fake)
    return g, fake


def test_a_timeout_falls_back_instead_of_crashing_and_the_model_rests():
    g, fake = client({"new": [httpx.ReadTimeout("slow")], "old": [ok("a"), ok("b")]})
    assert g.structured(["new", "old"], "sys", ["hi"], Answer).text == "a"
    assert g.structured(["new", "old"], "sys", ["hi"], Answer).text == "b"
    assert fake.tried == ["new", "old", "old"]  # no second wait on the slow model


def test_models_the_key_may_not_use_are_never_tried_again():
    g, fake = client({"gone": [api_error(404)], "ok": [ok(), ok()]})
    g.structured(["gone", "ok"], "sys", ["hi"], Answer)
    g.structured(["gone", "ok"], "sys", ["hi"], Answer)
    assert fake.tried == ["gone", "ok", "ok"]


def test_a_quick_overload_is_retried_once_on_the_same_model():
    g, fake = client({"busy": [api_error(503), ok("again")]})
    assert g.structured(["busy"], "sys", ["hi"], Answer).text == "again"


def test_an_unreadable_answer_tries_the_next_model():
    g, fake = client({"odd": [SimpleNamespace(parsed=None, usage_metadata=None)], "ok": [ok("fine")]})
    assert g.structured(["odd", "ok"], "sys", ["hi"], Answer).text == "fine"


def test_a_rate_limit_on_every_model_is_waited_out_once(monkeypatch):
    waits = []
    monkeypatch.setattr(gemini_mod.time, "sleep", waits.append)
    limit = errors.APIError(429, {"error": {"code": 429, "message": "x", "status": "X", "details": [
        {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "7s"}]}})
    g, fake = client({"m": [limit, limit, ok("later")]})
    assert g.structured(["m"], "sys", ["hi"], Answer).text == "later"
    assert 7.0 in waits and fake.tried == ["m", "m", "m"]


def test_when_every_model_fails_the_box_gets_a_runtime_error():
    g, _ = client({"a": [api_error(404)], "b": [httpx.ReadTimeout("slow")]})
    with pytest.raises(RuntimeError):
        g.structured(["a", "b"], "sys", ["hi"], Answer)
