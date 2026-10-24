"""Vercel AI Gateway client and key selection, without the network."""

import json

import httpx
import pytest

from box.brain import llm
from box.brain.gateway import Gateway, json_schema
from box.brain.llm import Image, NoKey, make_llm
from box.brain.schemas import Plan, Turn

TURN = {"need_screenshot": False, "done": True, "success": True, "message": "Alarm set.", "actions": []}


def test_schema_is_strict_and_self_contained():
    s = json_schema(Turn)
    assert "$defs" not in json.dumps(s) and "$ref" not in json.dumps(s)
    assert s["additionalProperties"] is False and set(s["required"]) == set(Turn.model_fields)
    action = s["properties"]["actions"]["items"]
    assert action["additionalProperties"] is False and "kind" in action["required"]
    assert "enum" in action["properties"]["kind"]


def gateway(handler) -> Gateway:
    return Gateway("test-key", transport=httpx.MockTransport(handler))


def reply(obj, tokens=(1200, 80)) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(obj)}}],
                                     "usage": {"prompt_tokens": tokens[0], "completion_tokens": tokens[1]}})


def test_request_shape_and_answer():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers["authorization"]
        seen["body"] = json.loads(request.content)
        return reply(TURN)

    g = gateway(handler)
    turn = g.structured(["gemini-3.8-flash"], "system", ["screen text", Image("QUJD")], Turn)
    body = seen["body"]
    assert seen["auth"] == "Bearer test-key"
    assert body["model"] == "google/gemini-3.8-flash"
    assert body["reasoning"] == {"effort": "low", "exclude": True}
    assert body["response_format"]["json_schema"]["strict"] is True
    user = body["messages"][1]["content"]
    assert user[0] == {"type": "text", "text": "screen text"}
    assert user[1]["image_url"]["url"] == "data:image/jpeg;base64,QUJD"
    assert turn.message == "Alarm set." and (g.calls, g.input_tokens, g.output_tokens) == (1, 1200, 80)


def test_overload_retries_then_falls_back_to_the_next_model():
    tried = []

    def handler(request: httpx.Request) -> httpx.Response:
        model = json.loads(request.content)["model"]
        tried.append(model)
        return httpx.Response(503, text="busy") if model.endswith("3.8-flash") else reply(TURN)

    g = gateway(handler)
    g.structured(["gemini-3.8-flash", "gemini-3.5-flash"], "s", ["x"], Turn)
    assert tried == ["google/gemini-3.8-flash", "google/gemini-3.8-flash", "google/gemini-3.5-flash"]


def test_a_rate_limit_is_waited_out_once(monkeypatch):
    from box.brain import gateway as gateway_mod
    waits, replies = [], [httpx.Response(429, headers={"retry-after": "9"}, text="limit")] * 2 + [reply(TURN)]
    monkeypatch.setattr(gateway_mod.time, "sleep", waits.append)
    gateway(lambda request: replies.pop(0)).structured(["gemini-2.5-flash"], "s", ["x"], Turn)
    assert waits == [0.8, 9.0] and replies == []


def test_no_credit_is_reported_not_retried():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(402, json={"error": {"message": "insufficient credits"}})

    with pytest.raises(RuntimeError, match="402"):
        gateway(handler).structured(["gemini-3.8-flash"], "s", ["x"], Plan)
    assert len(calls) == 1


def test_key_choice(tmp_path, monkeypatch):
    monkeypatch.setattr(llm, "STATE", tmp_path)
    for env in ("NEXTSTEP_BOX_GEMINI_KEY", "NEXTSTEP_BOX_AI_GATEWAY_KEY", "NEXTSTEP_BOX_LLM"):
        monkeypatch.delenv(env, raising=False)
    with pytest.raises(NoKey):
        make_llm()
    (tmp_path / "ai-gateway.key").write_text("gw-key\n")
    assert type(make_llm()).__name__ == "Gateway"
    (tmp_path / "gemini.key").write_text("gem-key")
    assert type(make_llm()).__name__ == "Gemini"  # direct is one hop shorter
    monkeypatch.setenv("NEXTSTEP_BOX_LLM", "gateway")
    assert type(make_llm()).__name__ == "Gateway"


def test_models_the_account_cannot_use_are_skipped_after_the_first_refusal():
    tried = []

    def handler(request: httpx.Request) -> httpx.Response:
        model = json.loads(request.content)["model"]
        tried.append(model)
        if model != "google/gemini-2.5-flash":
            return httpx.Response(403, json={"error": {"message": "Free tier users do not have access to this model."}})
        return reply(TURN)

    g = gateway(handler)
    models = ["gemini-3.8-flash", "gemini-3.5-flash", "gemini-2.5-flash"]
    g.structured(models, "s", ["x"], Turn)
    g.structured(models, "s", ["x"], Turn)
    assert tried == ["google/gemini-3.8-flash", "google/gemini-3.5-flash", "google/gemini-2.5-flash", "google/gemini-2.5-flash"]
