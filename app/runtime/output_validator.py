"""Deterministic output-contract validation for agent answers."""
from __future__ import annotations

import re
from typing import Any

from app.core.schemas import AgentAnswer, OutputContract

NUM = re.compile(r"(?<![A-Za-z])\d+(?:[.,]\d+)*")


def numbers_in(text: str) -> set[str]:
    out = set()
    for m in NUM.findall(text or ""):
        v = m.replace(",", "")
        v = v.rstrip(".")
        if v:
            try:
                f = float(v)
                out.add(str(int(f)) if f.is_integer() else str(f))
            except ValueError:
                continue
    return out


def unsupported_numbers(answer: str, evidence_texts: list[str], question: str = "") -> set[str]:
    """Numbers in the answer that appear neither in the evidence, the tool outputs nor the question."""
    known = set()
    for t in evidence_texts + [question]:
        known |= numbers_in(t)
    return {n for n in numbers_in(answer) if n not in known and n not in {"0", "1"}}


def validate_answer(raw_keys: set[str], ans: AgentAnswer, contract: OutputContract,
                    allowed_sources: set[str]) -> tuple[AgentAnswer, list[str]]:
    """Returns a cleaned answer and the list of contract violations found."""
    errors: list[str] = []
    missing = [f for f in contract.required_fields if f not in raw_keys]
    if missing:
        errors.append(f"missing required fields: {missing}")
    if not ans.answer.strip():
        errors.append("empty answer text")
    bad = [c for c in ans.citations if _match_source(c, allowed_sources) is None]
    if bad:
        errors.append(f"citations not in retrieved evidence: {bad}")
    cleaned = []
    for c in ans.citations:
        m = _match_source(c, allowed_sources)
        if m and m not in cleaned:
            cleaned.append(m)
    ans = ans.model_copy(update={"citations": cleaned})
    if not ans.refused and not ans.needs_clarification and not ans.citations:
        errors.append("factual answer without any valid citation")
    if ans.refused and not ans.refusal_reason.strip():
        errors.append("refusal without refusal_reason")
    words = len(ans.answer.split())
    if words > contract.max_answer_words * 1.5:
        errors.append(f"answer too long ({words} words > {contract.max_answer_words})")
    return ans, errors


def _match_source(citation: str, allowed: set[str]) -> str | None:
    c = citation.strip().strip("[]()'\"").lower()
    for s in allowed:
        sl = s.lower()
        if c == sl or sl in c or (c and c in sl and len(c) >= 5) or c.split(",")[0].strip() == sl:
            return s
    return None


def capture_keys(store: dict[str, Any]):
    def hook(data: Any) -> Any:
        store["keys"] = set(data.keys()) if isinstance(data, dict) else set()
        return data
    return hook
