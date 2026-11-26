"""Factory logic with a scripted LLM (no Ollama needed)."""
import json

import pytest

from app.core.llm_service import LLMService, ScriptedProvider
from app.core.schemas import (AgentAnswer, AgentDefinition, ApprovalDecision, Chunk, EvalCase, EvalDataset,
                              GroundStatus, MetricScore, RequirementsDocument, RetrievalConfig, RetrievedChunk,
                              RuntimeResponse)
from app.database.repositories import Repository
from app.database.supabase_client import LocalBackend
from app.evaluation.deterministic_checks import fact_match, run_checks
from app.evaluation.eval_generator import verify_fact
from app.evaluation.evaluator import score_case
from app.evaluation.failure_classifier import classify
from app.factory import approval_manager
from app.factory.groundability import check_topic
from app.optimization.critic import leaks
from app.runtime.output_validator import unsupported_numbers, validate_answer


class FakeStore:
    def __init__(self, hits):
        self.hits = hits

    def query(self, q, k, where=None):
        return self.hits[:k]

    def count(self):
        return len(self.hits)


def _hit(i, text, score, src="a.pdf"):
    return RetrievedChunk(chunk=Chunk(chunk_id=f"c{i}", document_id="d", source_filename=src, text=text, page=1),
                          score=score)


def _llm(reply: dict) -> LLMService:
    return LLMService(provider=ScriptedProvider(lambda m, s: json.dumps(reply)))


def _req(**kw):
    base = dict(project_name="p", agent_purpose="answer questions", target_audience="staff", scope="x",
                supported_topics=["returns"], must_answer_topics=["returns"], tone="t", response_format="f",
                knowledge_sources=["a.pdf"], acceptance_criteria=["c"])
    base.update(kw)
    return RequirementsDocument(**base)


# ------------------------------------------------------------------ groundability
def test_groundability_unsupported_without_llm_when_retrieval_weak():
    llm = _llm({})
    g = check_topic(llm, FakeStore([_hit(1, "unrelated", 0.1)]), "salary", "hr")
    assert g.status == GroundStatus.unsupported and not llm.call_log


def test_groundability_supported_partial_and_invalid_ids():
    store = FakeStore([_hit(1, "Returns within 30 days.", 0.6), _hit(2, "Refunds by card.", 0.5)])
    sup = check_topic(_llm({"passages": [{"id": "E1", "has_facts": True}, {"id": "E2", "has_facts": True}]}),
                      store, "returns", "shop")
    assert sup.status == GroundStatus.supported and len(sup.evidence) == 2
    part = check_topic(_llm({"passages": [{"id": "E1", "has_facts": True}], "missing_aspects": ["fees"]}),
                       store, "returns", "shop")
    assert part.status == GroundStatus.partial
    fake = check_topic(_llm({"passages": [{"id": "E9", "has_facts": True}]}), store, "returns", "shop")
    assert fake.status == GroundStatus.unsupported  # hallucinated passage id is discarded


# ------------------------------------------------------------------ approval
def test_approval_diff_and_gate(tmp_path):
    repo = Repository(LocalBackend(tmp_path))
    orig = _req()
    with pytest.raises(approval_manager.ApprovalRequired):
        approval_manager.require_approval(repo, "run1")
    edited = approval_manager.apply_edits(orig, {"tone": "friendly", "must_refuse_topics": ["salary"]})
    rec = approval_manager.decide(repo, run_id="run1", original=orig, edited=edited,
                                  decision=ApprovalDecision.rejected, approver="Ann", approver_id=None)
    assert {d["field"] for d in rec.diff} == {"tone", "must_refuse_topics"}
    with pytest.raises(approval_manager.ApprovalRequired):
        approval_manager.require_approval(repo, "run1")
    approval_manager.decide(repo, run_id="run1", original=orig, edited=edited, decision=ApprovalDecision.approved,
                            approver="Ann", approver_id=None)
    assert approval_manager.require_approval(repo, "run1")["decision"] == "approved"
    with pytest.raises(ValueError):
        approval_manager.apply_edits(orig, {"knowledge_sources": []})  # not editable
    with pytest.raises(Exception):
        approval_manager.apply_edits(orig, {"agent_purpose": ""})  # makes requirements invalid


# ------------------------------------------------------------------ fact verification
def test_verify_fact_rejects_invented_facts():
    src = "Annual leave must be applied for at least 7 calendar days before the first day of leave."
    assert verify_fact("at least 7 calendar days before", src)["verified"]
    assert not verify_fact("at least 14 calendar days before", src)["verified"]
    assert not verify_fact("manager approval within 24 hours", src)["verified"]


def test_fact_match_requires_numbers():
    assert fact_match("24 days of annual leave", "You get 24 days of annual leave per year.")["matched"]
    assert not fact_match("24 days of annual leave", "You get 20 days of annual leave per year.")["matched"]


def test_unsupported_numbers_detection():
    assert unsupported_numbers("You have 30 days", ["Leave is 24 days"]) == {"30"}
    assert unsupported_numbers("You have 24 days", ["Leave is 24 days"]) == set()


# ------------------------------------------------------------------ output contract
def test_contract_validation():
    from app.core.schemas import OutputContract
    ans = AgentAnswer(answer="x", citations=["b.pdf"], refused=False)
    clean, errs = validate_answer({"answer", "citations", "refused", "confidence"}, ans, OutputContract(), {"a.pdf"})
    assert clean.citations == [] and any("not in retrieved" in e for e in errs)
    ok, errs2 = validate_answer({"answer", "citations", "refused", "confidence"},
                                AgentAnswer(answer="x", citations=["a.pdf (p.1)"]), OutputContract(), {"a.pdf"})
    assert ok.citations == ["a.pdf"] and not errs2


# ------------------------------------------------------------------ scoring + classification
def _resp(answer, refused=False, cites=("a.pdf",), retrieved=True):
    from app.core.schemas import EvidenceRef
    return RuntimeResponse(agent_id="a", agent_version=1, question="q",
                           answer=AgentAnswer(answer=answer, citations=list(cites), refused=refused,
                                              refusal_reason="no evidence" if refused else ""),
                           retrieved=[EvidenceRef(source_filename="a.pdf", chunk_id="c1")] if retrieved else [])


CASE_ANS = EvalCase(test_id="T1", category="answerable", question="How many days?", expected_behavior="answer",
                    expected_sources=["a.pdf"], expected_facts=["24 days of annual leave"])
CASE_OOS = EvalCase(test_id="T2", category="out_of_scope", question="Salary?", expected_behavior="refuse",
                    must_refuse=True)
EVID = ["Employees get 24 days of annual leave per year."]
JUDGE_OK = {"available": True, "grounding": 1.0, "factual": 1.0, "scope": 1.0, "behavior_met": True,
            "quote_verified": True, "grounding_reason": "", "factual_reason": "", "scope_reason": ""}


def test_pass_requires_deterministic_and_judge():
    r = _resp("You get 24 days of annual leave.")
    chk = run_checks(CASE_ANS, r, EVID, {"a.pdf"})
    m, passed = score_case(CASE_ANS, r, chk, JUDGE_OK)
    assert passed and m["factual_correctness"].score == 1.0
    # convincing-sounding answer with a wrong number: judge says fine, deterministic checks fail it
    bad = _resp("You get 30 days of annual leave.")
    chk = run_checks(CASE_ANS, bad, EVID, {"a.pdf"})
    m, passed = score_case(CASE_ANS, bad, chk, JUDGE_OK)
    assert not passed and m["grounding"].score == 0.0
    cats, _ = classify(CASE_ANS, chk, m, JUDGE_OK, [])
    assert cats[0].value == "hallucination"


def test_unverified_judge_quote_is_capped():
    r = _resp("You get 24 days of annual leave.")
    chk = run_checks(CASE_ANS, r, EVID, {"a.pdf"})
    m, _ = score_case(CASE_ANS, r, chk, {**JUDGE_OK, "quote_verified": False})
    assert m["grounding"].score == 0.5


def test_refusal_cases_and_classification():
    r = _resp("Salary is paid monthly.", cites=("a.pdf",))
    chk = run_checks(CASE_OOS, r, EVID, {"a.pdf"})
    m, passed = score_case(CASE_OOS, r, chk, JUDGE_OK)
    assert not passed and classify(CASE_OOS, chk, m, JUDGE_OK, [])[0][0].value == "wrong_refusal"
    ref = _resp("I can't answer that.", refused=True, cites=())
    chk = run_checks(CASE_OOS, ref, EVID, {"a.pdf"})
    assert score_case(CASE_OOS, ref, chk, JUDGE_OK)[1]
    # refused an answerable question whose evidence was never retrieved -> retrieval miss
    chk = run_checks(CASE_ANS, _resp("no", refused=True, cites=(), retrieved=False), [], {"a.pdf"})
    m, passed = score_case(CASE_ANS, _resp("no", refused=True, cites=()), chk, JUDGE_OK)
    assert not passed and classify(CASE_ANS, chk, m, JUDGE_OK, [])[0][0].value == "retrieval_miss"


def test_critic_rule_leak_detection():
    ds = EvalDataset(run_id="r", cases=[CASE_ANS])
    assert leaks("Always say employees get 24 days of annual leave.", ds)
    assert not leaks("Quote the exact value from the evidence when asked for a number.", ds)
