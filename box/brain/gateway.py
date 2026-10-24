"""Gemini through Vercel AI Gateway's OpenAI-compatible API (https://ai-gateway.vercel.sh/v1).

Free Vercel accounts get $5 of AI Gateway credit every 30 days. One persistent HTTPS connection;
brief overloads (429/5xx) are retried once, then the next model in the list is tried.
"""

import time
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from .llm import Image

T = TypeVar("T", bound=BaseModel)
BASE_URL = "https://ai-gateway.vercel.sh/v1"
RETRY = {429, 500, 502, 503, 504}


def model_id(name: str) -> str:
    """'gemini-3.8-flash' -> 'google/gemini-3.8-flash'; names that already say the creator stay as they are."""
    return name if "/" in name else f"google/{name}"


def json_schema(schema: type[BaseModel]) -> dict[str, Any]:
    """Pydantic's JSON schema in the strict form structured output wants: $refs inlined, every
    property required, no extra properties."""
    raw = schema.model_json_schema()
    defs = raw.pop("$defs", {})

    def walk(node: Any) -> Any:
        if isinstance(node, list):
            return [walk(v) for v in node]
        if not isinstance(node, dict):
            return node
        if "$ref" in node:
            return walk(defs[node["$ref"].rsplit("/", 1)[-1]])
        out = {k: ({name: walk(s) for name, s in v.items()} if k == "properties" else walk(v))
               for k, v in node.items() if k != "title"}
        if out.get("type") == "object":
            out["additionalProperties"] = False
            out["required"] = list(out.get("properties", {}))
        return out

    return walk(raw)


def _json_text(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):  # some models wrap JSON in a code fence
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0]
    return text


class Gateway:
    def __init__(self, key: str, timeout_s: float = 30.0, transport: httpx.BaseTransport | None = None):
        self.http = httpx.Client(base_url=BASE_URL, headers={"Authorization": f"Bearer {key}"},
                                 timeout=timeout_s, transport=transport)
        self.calls = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self._schemas: dict[type, dict[str, Any]] = {}
        self.unavailable: set[str] = set()  # models this account may not use (e.g. not in the free tier)

    def structured(self, models: list[str], system: str, parts: list, schema: type[T], thinking: str = "LOW") -> T:
        if schema not in self._schemas:
            self._schemas[schema] = json_schema(schema)
        content = [{"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{p.jpeg_b64}"}}
                   if isinstance(p, Image) else {"type": "text", "text": str(p)} for p in parts]
        body = {
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": content}],
            "response_format": {"type": "json_schema",
                                "json_schema": {"name": schema.__name__, "strict": True, "schema": self._schemas[schema]}},
            "reasoning": {"effort": thinking.lower(), "exclude": True},
        }
        last: object = None
        for model in [m for m in models if model_id(m) not in self.unavailable]:
            for attempt in range(2):
                try:
                    r = self.http.post("/chat/completions", json={"model": model_id(model), **body})
                except httpx.TransportError as e:
                    last = e
                    if attempt == 0:
                        time.sleep(0.5)
                        continue
                    break
                if r.status_code != 200:
                    last = f"{model_id(model)}: HTTP {r.status_code} {r.text[:200]}"
                    if r.status_code == 403 and "do not have access to this model" in r.text:
                        self.unavailable.add(model_id(model))  # skip it from now on
                    if r.status_code in RETRY and attempt == 0:
                        time.sleep(0.8)
                        continue
                    break  # other errors, or a second failure: try the next model
                data = r.json()
                self._count(data)
                try:
                    return schema.model_validate_json(_json_text(data["choices"][0]["message"].get("content") or ""))
                except (ValidationError, KeyError, IndexError) as e:
                    last = f"{model_id(model)}: unusable answer ({e.__class__.__name__})"
                    break
        raise RuntimeError(f"Model unavailable: {last}")

    def _count(self, data: dict[str, Any]) -> None:
        self.calls += 1
        u = data.get("usage") or {}
        self.input_tokens += int(u.get("prompt_tokens") or 0)
        self.output_tokens += int(u.get("completion_tokens") or 0)
