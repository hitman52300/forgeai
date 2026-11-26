"""Tracks real resource consumption of a factory run and enforces limits."""
from __future__ import annotations

import threading
import time

from app.core.schemas import BudgetLimits, BudgetUsage


class BudgetExceeded(RuntimeError):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class BudgetManager:
    def __init__(self, limits: BudgetLimits | None = None, usage: BudgetUsage | None = None):
        self.limits = limits or BudgetLimits()
        self.usage = usage or BudgetUsage()
        self._start = time.monotonic() - self.usage.elapsed_seconds
        self._lock = threading.Lock()

    # ----------------------------------------------------------- accounting
    def record_call(self, stage: str, prompt_tokens: int, completion_tokens: int) -> None:
        with self._lock:
            self.usage.llm_calls += 1
            self.usage.prompt_tokens += int(prompt_tokens or 0)
            self.usage.completion_tokens += int(completion_tokens or 0)
            self.usage.calls_by_stage[stage] = self.usage.calls_by_stage.get(stage, 0) + 1
            self.usage.elapsed_seconds = round(time.monotonic() - self._start, 2)

    def record_iteration(self) -> None:
        self.usage.iterations += 1

    def tick(self) -> None:
        self.usage.elapsed_seconds = round(time.monotonic() - self._start, 2)

    # ----------------------------------------------------------- checks
    def exhausted_reason(self) -> str | None:
        self.tick()
        u, l = self.usage, self.limits
        if u.llm_calls >= l.max_llm_calls:
            return f"LLM call budget exhausted ({u.llm_calls}/{l.max_llm_calls} calls)"
        if u.total_tokens >= l.max_tokens:
            return f"token budget exhausted ({u.total_tokens}/{l.max_tokens} tokens)"
        if u.elapsed_seconds >= l.max_seconds:
            return f"time budget exhausted ({u.elapsed_seconds:.0f}s/{l.max_seconds}s)"
        return None

    def check(self) -> None:
        reason = self.exhausted_reason()
        if reason:
            raise BudgetExceeded(reason)

    def can_afford(self, estimated_calls: int, estimated_seconds: float = 0.0) -> tuple[bool, str]:
        """Used before starting an expensive step (e.g. a whole optimisation iteration)."""
        self.tick()
        u, l = self.usage, self.limits
        if u.llm_calls + estimated_calls > l.max_llm_calls:
            return False, (f"next step needs ~{estimated_calls} LLM calls but only "
                           f"{l.max_llm_calls - u.llm_calls} remain")
        if estimated_seconds and u.elapsed_seconds + estimated_seconds > l.max_seconds:
            return False, (f"next step needs ~{estimated_seconds:.0f}s but only "
                           f"{l.max_seconds - u.elapsed_seconds:.0f}s remain")
        avg_tokens = u.total_tokens / u.llm_calls if u.llm_calls else 0
        if avg_tokens and u.total_tokens + avg_tokens * estimated_calls > l.max_tokens:
            return False, "next step would exceed the token budget"
        return True, ""

    def snapshot(self) -> dict:
        self.tick()
        return {"limits": self.limits.model_dump(), "usage": self.usage.model_dump(),
                "total_tokens": self.usage.total_tokens}
