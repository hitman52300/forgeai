"""Deterministic (non-LLM) checks applied to every evaluated answer."""
from __future__ import annotations

from app.core.schemas import EvalCase, RuntimeResponse
from app.evaluation.eval_generator import content_tokens, norm
from app.runtime.output_validator import numbers_in, unsupported_numbers

REFUSAL_MARKERS = ("can't answer", "cannot answer", "can not answer", "unable to answer", "not able to answer",
                   "don't have information", "do not have information", "no information", "not covered",
                   "outside the scope", "outside my scope", "not in the approved", "cannot provide",
                   "can't provide", "not available in", "i can't help", "i cannot help")


def fact_match(fact: str, answer: str) -> dict:
    na, nf = norm(answer), norm(fact)
    if nf and nf in na:
        return {"fact": fact, "matched": True, "recall": 1.0, "numbers_ok": True}
    toks = content_tokens(fact)
    ans_toks = set(content_tokens(answer))
    recall = sum(t in ans_toks for t in toks) / len(toks) if toks else 0.0
    nums = numbers_in(fact)
    nums_ok = nums <= numbers_in(answer)
    return {"fact": fact, "matched": bool(recall >= 0.6 and nums_ok), "recall": round(recall, 2),
            "numbers_ok": nums_ok}


def looks_like_refusal(text: str) -> bool:
    t = text.lower()
    return any(m in t for m in REFUSAL_MARKERS)


def run_checks(case: EvalCase, resp: RuntimeResponse, evidence_texts: list[str], known_sources: set[str]) -> dict:
    ans = resp.answer
    refused = bool(ans.refused) or (looks_like_refusal(ans.answer) and not ans.citations)
    facts = [fact_match(f, ans.answer) for f in case.expected_facts]
    fact_recall = (sum(f["matched"] for f in facts) / len(facts)) if facts else None
    tool_texts = [str(t.output) for t in resp.tool_results if t.ok]
    unsupported = sorted(unsupported_numbers(ans.answer, evidence_texts + tool_texts, case.question)) \
        if not refused else []
    invalid_citations = [c for c in ans.citations if c not in known_sources]
    cited_expected = bool(set(ans.citations) & set(case.expected_sources)) if case.expected_sources else None
    # retrieval hit: did any retrieved passage contain an expected fact? (independent of chunking config)
    retrieval_hit = None
    if case.expected_facts:
        nev = [norm(t) for t in evidence_texts]
        retrieval_hit = any(any(norm(f) in e for e in nev) for f in case.expected_facts) or any(
            sum(t in set(content_tokens(e)) for t in content_tokens(f)) / max(1, len(content_tokens(f))) >= 0.85
            for f in case.expected_facts for e in evidence_texts)
    tool_errors = [f"{t.tool}: {t.error}" for t in resp.tool_results if not t.ok]
    return {
        "refused": refused,
        "refused_by": resp.refusal_applied_by,
        "needs_clarification": bool(ans.needs_clarification) or ("?" in ans.answer and not refused),
        "must_refuse": case.must_refuse,
        "refusal_ok": refused == case.must_refuse,
        "fact_matches": facts,
        "fact_recall": fact_recall,
        "unsupported_numbers": unsupported,
        "citations": ans.citations,
        "invalid_citations": invalid_citations,
        "cited_expected_source": cited_expected,
        "has_citation": bool(ans.citations),
        "contract_valid": resp.contract_valid,
        "contract_errors": resp.contract_errors,
        "retrieved_sources": sorted({r.source_filename for r in resp.retrieved}),
        "retrieved_count": len(resp.retrieved),
        "expected_evidence_retrieved": retrieval_hit,
        "tool_calls": [t.tool for t in resp.tool_results],
        "tool_errors": tool_errors,
        "answer_words": len(ans.answer.split()),
    }
