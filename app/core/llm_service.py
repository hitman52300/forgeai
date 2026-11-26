"""Single LLM interface used by every component.

`LLMService` hides the provider. Only `OllamaProvider` is implemented today; a
new provider only has to implement `LLMProvider.chat`.  JSON generation is
validated against a Pydantic model and retried with the validation error fed
back to the model, because a small local model will not always comply.
"""
from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.config import Settings, get_settings
from app.core.budget_manager import BudgetManager

log = logging.getLogger("forgeai.llm")
T = TypeVar("T", bound=BaseModel)


class LLMError(RuntimeError):
    pass


@dataclass
class LLMResult:
    text: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    model: str = ""
    latency_s: float = 0.0


class LLMProvider(Protocol):
    def chat(self, messages: list[dict[str, str]], *, model: str, temperature: float, max_tokens: int,
             json_schema: dict | None = None, seed: int | None = None) -> LLMResult: ...


class OllamaProvider:
    def __init__(self, settings: Settings):
        self.s = settings
        self._client = httpx.Client(base_url=settings.ollama_base_url, timeout=settings.llm_timeout_s)

    def chat(self, messages, *, model, temperature, max_tokens, json_schema=None, seed=None) -> LLMResult:
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens, "num_ctx": self.s.llm_num_ctx},
        }
        if seed is not None:
            payload["options"]["seed"] = seed
        if json_schema is not None:
            payload["format"] = json_schema
        t0 = time.monotonic()
        try:
            r = self._client.post("/api/chat", json=payload)
        except httpx.HTTPError as e:
            raise LLMError(f"Ollama request failed: {e}") from e
        if r.status_code != 200:
            raise LLMError(f"Ollama returned HTTP {r.status_code}: {r.text[:300]}")
        data = r.json()
        return LLMResult(
            text=data.get("message", {}).get("content", ""),
            prompt_tokens=int(data.get("prompt_eval_count") or 0),
            completion_tokens=int(data.get("eval_count") or 0),
            model=model,
            latency_s=time.monotonic() - t0,
        )

    def list_models(self) -> list[str]:
        r = self._client.get("/api/tags")
        r.raise_for_status()
        return [m["name"] for m in r.json().get("models", [])]


class OpenRouterProvider:
    """OpenRouter (OpenAI-compatible) chat completions. By default only free (':free') models are allowed.

    Free models are rate limited by OpenRouter; HTTP 429/5xx are retried with backoff and, if
    configured, the request falls back to the next free model in OPENROUTER_FALLBACK_MODELS.
    """

    def __init__(self, settings: Settings):
        if not settings.openrouter_api_key:
            raise LLMError("OPENROUTER_API_KEY is not set in .env")
        self.s = settings
        self._client = httpx.Client(
            base_url=settings.openrouter_base_url.rstrip("/"), timeout=settings.llm_timeout_s,
            headers={"Authorization": f"Bearer {settings.openrouter_api_key}",
                     "X-Title": "ForgeAI", "Content-Type": "application/json"})

    def _check_free(self, model: str) -> None:
        if self.s.openrouter_free_only and not model.endswith(":free"):
            raise LLMError(f"model '{model}' is not a free model; OPENROUTER_FREE_ONLY=true allows only ':free' models")

    def chat(self, messages, *, model, temperature, max_tokens, json_schema=None, seed=None) -> LLMResult:
        candidates = [model] + [m for m in self.s.openrouter_fallback_list if m != model]
        last = ""
        for m in candidates:
            self._check_free(m)
            payload: dict[str, Any] = {"model": m, "messages": messages, "temperature": temperature,
                                       "max_tokens": max_tokens}
            if seed is not None:
                payload["seed"] = seed
            if isinstance(json_schema, dict):
                payload["response_format"] = {"type": "json_schema",
                                              "json_schema": {"name": "output", "strict": False,
                                                              "schema": json_schema}}
            elif json_schema is not None:
                payload["response_format"] = {"type": "json_object"}
            t0 = time.monotonic()
            for attempt in range(self.s.openrouter_rate_limit_retries + 1):
                try:
                    r = self._client.post("/chat/completions", json=payload)
                except httpx.HTTPError as e:
                    last = f"OpenRouter request failed: {e}"
                    time.sleep(min(30, 2 ** attempt))
                    continue
                if r.status_code == 400 and "response_format" in payload:
                    payload.pop("response_format")  # model does not support it: rely on prompt + validation
                    continue
                if r.status_code in (429, 500, 502, 503, 504):
                    last = f"OpenRouter HTTP {r.status_code} for {m}: {r.text[:200]}"
                    wait = float(r.headers.get("retry-after") or min(60, 5 * 2 ** attempt))
                    time.sleep(wait)
                    continue
                if r.status_code != 200:
                    raise LLMError(f"OpenRouter returned HTTP {r.status_code}: {r.text[:300]}")
                data = r.json()
                if data.get("error"):
                    last = f"OpenRouter error for {m}: {str(data['error'])[:200]}"
                    break
                choice = (data.get("choices") or [{}])[0]
                usage = data.get("usage") or {}
                return LLMResult(text=(choice.get("message") or {}).get("content") or "",
                                 prompt_tokens=int(usage.get("prompt_tokens") or 0),
                                 completion_tokens=int(usage.get("completion_tokens") or 0),
                                 model=data.get("model", m), latency_s=time.monotonic() - t0)
        raise LLMError(last or "OpenRouter request failed")

    def list_models(self) -> list[str]:
        r = self._client.get("/models")
        r.raise_for_status()
        ids = [m["id"] for m in r.json().get("data", [])]
        return [i for i in ids if i.endswith(":free")] if self.s.openrouter_free_only else ids


class ScriptedProvider:
    """Deterministic provider for unit tests: a function maps messages -> reply text."""

    def __init__(self, responder: Callable[[list[dict[str, str]], dict | None], str]):
        self.responder = responder
        self.calls: list[list[dict[str, str]]] = []

    def chat(self, messages, *, model, temperature, max_tokens, json_schema=None, seed=None) -> LLMResult:
        self.calls.append(messages)
        text = self.responder(messages, json_schema)
        return LLMResult(text=text, prompt_tokens=sum(len(m["content"]) // 4 for m in messages),
                         completion_tokens=len(text) // 4, model=model)


_JSON_BLOCK = re.compile(r"\{.*\}|\[.*\]", re.S)


def extract_json(text: str) -> Any:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?|```$", "", text).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = _JSON_BLOCK.search(text)
        if not m:
            raise
        return json.loads(m.group(0))


def load_prompt(name: str, settings: Settings | None = None) -> str:
    s = settings or get_settings()
    return (s.prompts_dir / name).read_text(encoding="utf-8")


def render(template: str, **values: Any) -> str:
    """Minimal {{name}} templating (no eval, no logic)."""
    def sub(m: re.Match) -> str:
        key = m.group(1).strip()
        v = values.get(key, "")
        return v if isinstance(v, str) else json.dumps(v, ensure_ascii=False, indent=1)
    return re.sub(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}", sub, template)


@dataclass
class LLMService:
    provider: LLMProvider
    settings: Settings = field(default_factory=get_settings)
    budget: BudgetManager | None = None
    call_log: list[dict] = field(default_factory=list)

    @classmethod
    def from_settings(cls, settings: Settings | None = None, budget: BudgetManager | None = None) -> "LLMService":
        s = settings or get_settings()
        providers = {"ollama": OllamaProvider, "openrouter": OpenRouterProvider}
        if s.llm_provider not in providers:
            raise LLMError(f"Unsupported LLM provider '{s.llm_provider}' (supported: {', '.join(providers)})")
        return cls(provider=providers[s.llm_provider](s), settings=s, budget=budget)

    # ------------------------------------------------------------------ text
    def complete(self, messages: list[dict[str, str]], *, stage: str, model: str | None = None,
                 temperature: float | None = None, max_tokens: int | None = None,
                 json_schema: dict | None = None) -> LLMResult:
        if self.budget:
            self.budget.check()
        model = model or self.settings.llm_model
        res = self.provider.chat(
            messages, model=model,
            temperature=self.settings.llm_temperature if temperature is None else temperature,
            max_tokens=max_tokens or self.settings.llm_max_tokens,
            json_schema=json_schema, seed=self.settings.llm_seed,
        )
        if self.budget:
            self.budget.record_call(stage, res.prompt_tokens, res.completion_tokens)
        self.call_log.append({"stage": stage, "model": model, "prompt_tokens": res.prompt_tokens,
                              "completion_tokens": res.completion_tokens, "latency_s": round(res.latency_s, 2)})
        return res

    # ------------------------------------------------------------------ JSON
    def generate_json(self, messages: list[dict[str, str]], schema: type[T], *, stage: str,
                      model: str | None = None, temperature: float | None = None,
                      max_tokens: int | None = None, use_schema_format: bool = True,
                      post_process: Callable[[Any], Any] | None = None) -> T:
        """Call the LLM until it returns JSON that validates against `schema`."""
        js = schema.model_json_schema() if use_schema_format else "json"
        msgs = list(messages)
        last_err = ""
        for attempt in range(1, self.settings.llm_max_retries + 1):
            res = self.complete(msgs, stage=stage, model=model, temperature=temperature,
                                max_tokens=max_tokens, json_schema=js)  # type: ignore[arg-type]
            try:
                data = extract_json(res.text)
                if post_process:
                    data = post_process(data)
                return schema.model_validate(data)
            except (json.JSONDecodeError, ValidationError, ValueError, TypeError) as e:
                last_err = str(e)[:800]
                log.warning("stage=%s attempt=%d invalid JSON: %s", stage, attempt, last_err[:200])
                msgs = list(messages) + [
                    {"role": "assistant", "content": res.text[:2000]},
                    {"role": "user", "content": "Your previous reply was invalid: " + last_err +
                     "\nReturn ONLY one corrected JSON object that satisfies the schema."},
                ]
        raise LLMError(f"[{stage}] model did not return valid JSON after "
                       f"{self.settings.llm_max_retries} attempts: {last_err}")

    def health(self) -> dict:
        try:
            models = self.provider.list_models()  # type: ignore[attr-defined]
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": str(e)}
        wanted = {self.settings.llm_model, self.settings.judge_model}
        missing = [m for m in wanted if m not in models and f"{m}:latest" not in models]
        return {"ok": not missing, "models": models, "missing": missing}
