"""Runs an agent against an evaluation dataset and scores every case."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Callable

from app.core.budget_manager import BudgetExceeded
from app.core.llm_service import LLMService
from app.core.schemas import (AgentAnswer, AgentDefinition, CaseResult, EvalCase, EvalDataset, EvidenceRef,
                              MetricScore, RuntimeResponse)
from app.evaluation.deterministic_checks import run_checks
from app.evaluation.failure_classifier import classify
from app.evaluation.llm_judge import judge
from app.runtime.chat_engine import AgentRuntime

log = logging.getLogger("forgeai.eval")


def score_case(case: EvalCase, resp: RuntimeResponse, checks: dict, jv: dict) -> tuple[dict[str, MetricScore], bool]:
    refused = checks["refused"]
    j_ok = jv.get("available", False)
    m: dict[str, MetricScore] = {}

    # refusal correctness (deterministic)
    if case.must_refuse:
        r = 1.0 if refused else 0.0
        expl = "refused as required" if refused else "answered a question that must be refused"
    elif case.subtype in ("ambiguous", "incomplete"):
        r = 1.0 if (not refused or checks["needs_clarification"]) else 0.5
        expl = "asked for clarification / answered" if r == 1 else "refused instead of clarifying"
    else:
        r = 0.0 if refused else 1.0
        expl = "answered a supported question" if not refused else "refused a supported question"
    m["refusal_correctness"] = MetricScore(score=r, explanation=expl)

    # output contract (deterministic)
    m["output_contract"] = MetricScore(score=1.0 if checks["contract_valid"] else 0.0,
                                       explanation="; ".join(checks["contract_errors"]) or "valid")

    answered = not refused
    # grounding: deterministic unsupported-number check AND (verified) judge score
    if answered:
        det = 0.0 if checks["unsupported_numbers"] else 1.0
        if j_ok:
            jg = jv["grounding"] if jv["quote_verified"] else min(jv["grounding"], 0.5)
            g = min(det, jg)
            expl = (f"deterministic={det} (unsupported numbers: {checks['unsupported_numbers'] or 'none'}); "
                    f"judge={jv['grounding']} quote_verified={jv['quote_verified']}: {jv['grounding_reason'][:200]}")
            method = "combined"
        else:
            g, expl, method = det, "judge unavailable; deterministic number check only", "deterministic"
        m["grounding"] = MetricScore(score=g, method=method, explanation=expl)
    else:
        m["grounding"] = MetricScore(score=1.0, applicable=False, explanation="refusal: no claims to ground")

    # factual correctness: deterministic fact recall combined with judge
    if case.expected_facts and answered:
        det = checks["fact_recall"] or 0.0
        if j_ok:
            f = round(0.5 * det + 0.5 * jv["factual"], 4)
            expl = f"fact recall={det:.2f}; judge={jv['factual']}: {jv['factual_reason'][:200]}"
            method = "combined"
        else:
            f, expl, method = det, f"fact recall={det:.2f} (judge unavailable)", "deterministic"
        m["factual_correctness"] = MetricScore(score=f, method=method, explanation=expl)
    elif case.expected_facts:
        m["factual_correctness"] = MetricScore(score=0.0, explanation="refused, so expected facts were not given")
    else:
        m["factual_correctness"] = MetricScore(score=0.0, applicable=False, explanation="no expected facts")

    # citation correctness (deterministic)
    if answered and (case.expected_sources or not checks["needs_clarification"]):
        if not checks["has_citation"]:
            c, expl = 0.0, "no citation"
        elif checks["invalid_citations"]:
            c, expl = 0.0, f"cites unknown sources {checks['invalid_citations']}"
        elif case.expected_sources:
            c = 1.0 if checks["cited_expected_source"] else 0.5
            expl = "cites an expected source" if c == 1 else "cites valid but unexpected sources"
        else:
            c, expl = 1.0, "valid citations"
        m["citation_correctness"] = MetricScore(score=c, explanation=expl)
    else:
        m["citation_correctness"] = MetricScore(score=1.0, applicable=False, explanation="no citation required")

    # scope adherence
    if case.must_refuse:
        m["scope_adherence"] = MetricScore(score=1.0 if refused else 0.0,
                                           explanation="stayed in scope by refusing" if refused
                                           else "answered an out-of-scope question")
    elif j_ok:
        m["scope_adherence"] = MetricScore(score=jv["scope"], method="llm_judge", explanation=jv["scope_reason"][:200])
    else:
        m["scope_adherence"] = MetricScore(score=0.0, applicable=False, explanation="judge unavailable")

    contract_ok = checks["contract_valid"]
    if case.must_refuse:
        passed = refused and contract_ok
    elif case.category.value == "answerable":
        passed = (answered and contract_ok and m["factual_correctness"].score >= 0.6
                  and m["grounding"].score >= 0.5 and m["citation_correctness"].score >= 0.5)
    else:  # edge cases
        behavior = bool(jv.get("behavior_met")) if j_ok else False
        if case.subtype in ("ambiguous", "incomplete"):
            behavior = behavior or checks["needs_clarification"]
            passed = behavior and contract_ok and (refused or m["grounding"].score >= 0.5)
        else:
            facts_ok = (not case.expected_facts) or m["factual_correctness"].score >= 0.5
            passed = behavior and answered and facts_ok and contract_ok and m["grounding"].score >= 0.5
    return m, bool(passed)


def evaluate(agent: AgentDefinition, agent_llm: LLMService, judge_llm: LLMService, dataset: EvalDataset, *,
             iteration: int, test_ids: list[str] | None = None,
             progress: Callable[[int, int, str], None] | None = None,
             checkpoint: Path | None = None) -> list[CaseResult]:
    runtime = AgentRuntime(agent, agent_llm)
    known = set(agent.knowledge_sources)
    cases = [c for c in dataset.cases if not test_ids or c.test_id in test_ids]
    # Phase 1: the agent answers every case. Phase 2: the judge grades every answer.
    # Batching by model avoids swapping the agent and judge models in GPU memory for every case.
    answered: list[tuple[EvalCase, RuntimeResponse, list[str]]] = []
    for i, case in enumerate(cases, start=1):
        if progress:
            progress(i, len(cases) * 2, f"answer {case.test_id}")
        try:
            resp = runtime.ask(case.question)
        except BudgetExceeded:
            raise
        except Exception as e:  # noqa: BLE001 - a crashing case is a recorded failure, not a crash of the run
            log.exception("runtime error on %s", case.test_id)
            resp = RuntimeResponse(agent_id=agent.agent_id, agent_version=agent.version, question=case.question,
                                   answer=AgentAnswer(answer=f"[runtime error: {e}]", refused=False, confidence=0),
                                   contract_valid=False, contract_errors=[f"runtime error: {e}"])
        evidence_texts = [c.text for c in runtime.retriever.store.get([r.chunk_id for r in resp.retrieved])]
        answered.append((case, resp, evidence_texts))
    results: list[CaseResult] = []
    for i, (case, resp, evidence_texts) in enumerate(answered, start=1):
        if progress:
            progress(len(cases) + i, len(cases) * 2, f"judge {case.test_id}")
        checks = run_checks(case, resp, evidence_texts, known)
        jv = judge(judge_llm, case, resp, evidence_texts)
        metrics, passed = score_case(case, resp, checks, jv)
        cats, why = ([], "") if passed else classify(case, checks, metrics, jv, agent.tools)
        r = CaseResult(test_id=case.test_id, category=case.category, question=case.question,
                       agent_version=agent.version, iteration=iteration, answer=resp.answer,
                       retrieved=resp.retrieved, metrics=metrics, deterministic_checks=checks,
                       judge=jv, passed=passed, failure_categories=cats, failure_explanation=why,
                       latency_s=resp.latency_s)
        results.append(r)
        if checkpoint:
            checkpoint.parent.mkdir(parents=True, exist_ok=True)
            with checkpoint.open("a", encoding="utf-8") as fh:
                fh.write(r.model_dump_json() + "\n")
    return results


def results_to_json(results: list[CaseResult]) -> list[dict]:
    return [json.loads(r.model_dump_json()) for r in results]
