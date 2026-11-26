import httpx
import pytest

from app.config import Settings
from app.core.llm_service import LLMError, OpenRouterProvider


def _provider(handler, **kw):
    s = Settings(llm_provider="openrouter", openrouter_api_key="test-key", openrouter_rate_limit_retries=1, **kw)
    p = OpenRouterProvider(s)
    p._client = httpx.Client(base_url="https://openrouter.test/api/v1", transport=httpx.MockTransport(handler))
    return p


def test_free_only_refuses_paid_models():
    p = _provider(lambda r: httpx.Response(200, json={}))
    with pytest.raises(LLMError, match="not a free model"):
        p.chat([{"role": "user", "content": "x"}], model="openai/gpt-4o", temperature=0, max_tokens=10)


def test_json_schema_request_and_usage(monkeypatch):
    seen = {}

    def handler(req):
        import json
        seen.update(json.loads(req.content))
        return httpx.Response(200, json={"model": "a:free", "choices": [{"message": {"content": "{\"a\": 1}"}}],
                                         "usage": {"prompt_tokens": 7, "completion_tokens": 3}})
    p = _provider(handler)
    res = p.chat([{"role": "user", "content": "x"}], model="a:free", temperature=0.1, max_tokens=50,
                 json_schema={"type": "object"})
    assert res.text == '{"a": 1}' and res.prompt_tokens == 7 and res.completion_tokens == 3
    assert seen["response_format"]["type"] == "json_schema" and seen["max_tokens"] == 50


def test_rate_limit_falls_back_to_next_free_model(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    calls = []

    def handler(req):
        import json
        m = json.loads(req.content)["model"]
        calls.append(m)
        if m == "a:free":
            return httpx.Response(429, headers={"retry-after": "0"}, text="rate limited")
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}], "usage": {}})
    p = _provider(handler, openrouter_fallback_models="b:free")
    assert p.chat([{"role": "user", "content": "x"}], model="a:free", temperature=0, max_tokens=5).text == "ok"
    assert calls[-1] == "b:free" and calls.count("a:free") == 2
