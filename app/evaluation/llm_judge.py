"""LLM-as-judge with bias defences.

* separate judge model (configurable) from the agent model -> self-preference bias
* single-answer absolute grading with a fixed rubric; for pairwise comparisons
  `pairwise_preference` judges both orders and only counts consistent verdicts -> position bias
* rubric states that length earns nothing; deterministic word-limit check -> verbosity bias
* the judge must quote the evidence; the quote is verified, and an unverifiable
  grounding score is capped -> judge hallucination
* key facts are given as "points to check", not as a reference answer
"""
from __future__ import annotations

import random

from pydantic import BaseModel, Field, field_validator

from app.config import get_settings
from app.core.llm_service import LLMError, LLMService, load_prompt, render
from app.core.schemas import EvalCase, RuntimeResponse
from app.evaluation.eval_generator import norm


class JudgeVerdict(BaseModel):
    grounding: float
    grounding_reason: str = ""
    factual: float
    factual_reason: str = ""
    scope: float
    scope_reason: str = ""
    behavior_met: bool
    behavior_reason: str = ""
    supporting_quote: str = ""
    unsupported_claims: list[str] = Field(default_factory=list)

    @field_validator("grounding", "factual", "scope", mode="before")
    @classmethod
    def _snap(cls, v):
        try:
            f = float(v)
        except (TypeError, ValueError):
            return 0.0
        if f > 1:
            f = f / 10 if f <= 10 else 1.0
        return min((0.0, 0.5, 1.0), key=lambda x: abs(x - f))


def judge(llm: LLMService, case: EvalCase, resp: RuntimeResponse, evidence_texts: list[str]) -> dict:
    s = get_settings()
    key_points = "\n".join(f"- {f}" for f in case.expected_facts) or "- (none: judge the behaviour)"
    evidence = "\n\n".join(f"[{i + 1}] {t[:1200]}" for i, t in enumerate(evidence_texts)) or "(no evidence retrieved)"
    prompt = render(load_prompt("judge.txt"), question=case.question, expected_behavior=case.expected_behavior,
                    key_points=key_points, evidence=evidence, answer=resp.answer.answer,
                    refused=str(resp.answer.refused).lower(), clarify=str(resp.answer.needs_clarification).lower(),
                    citations=", ".join(resp.answer.citations) or "none")
    try:
        v = llm.generate_json([{"role": "user", "content": prompt}], JudgeVerdict, stage="judge",
                              model=s.judge_model, temperature=0.0, max_tokens=600)
    except LLMError as e:
        return {"available": False, "error": str(e)[:300]}
    quote_ok = bool(v.supporting_quote.strip()) and norm(v.supporting_quote) in norm(" ".join(evidence_texts))
    out = v.model_dump()
    out.update({"available": True, "model": s.judge_model, "quote_verified": quote_ok})
    return out


class _Pref(BaseModel):
    better: str  # "A" | "B" | "tie"
    reason: str = ""


PAIR_PROMPT = """Two assistants answered the same question using the same evidence. Decide which answer is
better on correctness and grounding in the evidence only. Length and style do not matter.

QUESTION: {q}
EVIDENCE:
{e}

ANSWER A:
{a}

ANSWER B:
{b}

Return only JSON: {{"better": "A" | "B" | "tie", "reason": "..."}}"""


def pairwise_preference(llm: LLMService, question: str, evidence: str, ans_x: str, ans_y: str,
                        seed: int = 0) -> dict:
    """Judge (x, y) in both orders; returns 'x', 'y', 'tie' or 'inconsistent'."""
    s = get_settings()
    rng = random.Random(seed)
    orders = [(ans_x, ans_y, "x", "y"), (ans_y, ans_x, "y", "x")]
    rng.shuffle(orders)  # randomise which order is asked first
    votes = []
    for a, b, la, lb in orders:
        try:
            p = llm.generate_json([{"role": "user", "content": PAIR_PROMPT.format(q=question, e=evidence[:3000],
                                                                                 a=a, b=b)}],
                                  _Pref, stage="judge_pairwise", model=s.judge_model, temperature=0.0,
                                  max_tokens=250)
        except LLMError:
            votes.append("error")
            continue
        votes.append({"A": la, "B": lb}.get(p.better.strip().upper(), "tie"))
    if votes[0] == votes[1]:
        return {"winner": votes[0], "votes": votes}
    return {"winner": "inconsistent", "votes": votes}
