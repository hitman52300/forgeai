"""Deterministic failure classification (explainable decision rules).

Order matters: the first matching rule is the primary category; secondary
categories are kept when they also clearly apply.
"""
from __future__ import annotations

from app.core.schemas import EvalCase, FailureCategory, MetricScore


def classify(case: EvalCase, checks: dict, metrics: dict[str, MetricScore], judge: dict,
             agent_tools: list[str]) -> tuple[list[FailureCategory], str]:
    cats: list[FailureCategory] = []
    why: list[str] = []

    if not checks["contract_valid"]:
        cats.append(FailureCategory.output_contract)
        why.append("output contract violated: " + "; ".join(checks["contract_errors"])[:200])

    if checks["tool_errors"]:
        cats.append(FailureCategory.tool_defect)
        why.append("tool execution failed: " + "; ".join(checks["tool_errors"])[:200])

    refused = checks["refused"]
    if case.must_refuse and not refused:
        cats.append(FailureCategory.wrong_refusal)
        why.append("answered a question that must be refused")
    elif not case.must_refuse and refused and case.subtype not in ("ambiguous", "incomplete"):
        if checks["expected_evidence_retrieved"] is False:
            cats.append(FailureCategory.retrieval_miss)
            why.append("refused because the relevant passage was not retrieved")
        else:
            cats.append(FailureCategory.wrong_refusal)
            why.append("refused although supporting evidence was retrieved")

    if not refused and not case.must_refuse:
        hallucinated = bool(checks["unsupported_numbers"]) or (judge.get("available") and judge.get("grounding", 1) == 0)
        fact = metrics.get("factual_correctness")
        fact_bad = fact is not None and fact.applicable and fact.score < 0.6
        if fact_bad and checks["expected_evidence_retrieved"] is False:
            cats.append(FailureCategory.retrieval_miss)
            why.append("expected facts were not in the retrieved passages")
        if hallucinated:
            cats.append(FailureCategory.hallucination)
            detail = checks["unsupported_numbers"] or judge.get("unsupported_claims", [])[:2]
            why.append(f"unsupported content in answer: {detail}")
        if fact_bad and checks["expected_evidence_retrieved"] and not hallucinated:
            cats.append(FailureCategory.prompt_defect)
            why.append("evidence was retrieved but the answer missed the key facts")
        cit = metrics.get("citation_correctness")
        if cit is not None and cit.applicable and cit.score < 0.5 and FailureCategory.output_contract not in cats:
            cats.append(FailureCategory.prompt_defect)
            why.append("missing or wrong citations")
        if case.category.value == "edge_case" and judge.get("available") and not judge.get("behavior_met", True):
            if FailureCategory.prompt_defect not in cats:
                cats.append(FailureCategory.prompt_defect)
            why.append(f"edge-case behaviour not met: {judge.get('behavior_reason', '')[:150]}")

    needs_calc = any(k in case.question.lower() for k in ("calculate", "total cost", "sum of", "difference between",
                                                          "multiply", "in total"))
    if needs_calc and "calculator" in agent_tools and "calculator" not in checks["tool_calls"] and \
            FailureCategory.prompt_defect in cats:
        cats.append(FailureCategory.tool_defect)
        why.append("calculation question answered without the attached calculator")

    if not cats:
        cats.append(FailureCategory.prompt_defect)
        why.append("did not meet the pass criteria (see metric explanations)")
    dedup = list(dict.fromkeys(cats))
    return dedup, " | ".join(why)
