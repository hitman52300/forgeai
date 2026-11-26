import json

import pytest
from pydantic import BaseModel, ValidationError

from app.core.budget_manager import BudgetExceeded, BudgetManager
from app.core.llm_service import LLMError, LLMService, ScriptedProvider, extract_json, render
from app.core.schemas import (AgentAnswer, AgentDefinition, BudgetLimits, EvalCase, RequirementsDocument,
                              RetrievalConfig)
from app.database.repositories import Repository
from app.database.supabase_client import LocalBackend, StorageError


class Tiny(BaseModel):
    name: str
    n: int


def test_extract_json_variants():
    assert extract_json('{"a": 1}') == {"a": 1}
    assert extract_json('```json\n{"a": 2}\n```') == {"a": 2}
    assert extract_json('Sure! here: {"a": 3} thanks') == {"a": 3}


def test_generate_json_retries_then_succeeds():
    replies = iter(["not json at all", '{"name": "x"}', '{"name": "x", "n": 4}'])
    svc = LLMService(provider=ScriptedProvider(lambda m, s: next(replies)))
    out = svc.generate_json([{"role": "user", "content": "go"}], Tiny, stage="t")
    assert out == Tiny(name="x", n=4)
    assert len(svc.call_log) == 3


def test_generate_json_gives_up():
    svc = LLMService(provider=ScriptedProvider(lambda m, s: "nope"))
    with pytest.raises(LLMError):
        svc.generate_json([{"role": "user", "content": "go"}], Tiny, stage="t")


def test_budget_enforced():
    b = BudgetManager(BudgetLimits(max_llm_calls=2))
    svc = LLMService(provider=ScriptedProvider(lambda m, s: '{"name":"a","n":1}'), budget=b)
    svc.generate_json([{"role": "user", "content": "x"}], Tiny, stage="s")
    svc.generate_json([{"role": "user", "content": "x"}], Tiny, stage="s")
    with pytest.raises(BudgetExceeded):
        svc.generate_json([{"role": "user", "content": "x"}], Tiny, stage="s")
    assert b.usage.llm_calls == 2 and b.usage.calls_by_stage["s"] == 2
    ok, why = b.can_afford(5)
    assert not ok and "remain" in why


def test_render_template():
    assert render("Hi {{ name }} {{obj}}", name="A", obj={"k": 1}).startswith("Hi A {")


def test_requirements_validation_rejects_incomplete():
    with pytest.raises(ValidationError):
        RequirementsDocument(project_name="p", agent_purpose="", target_audience="a", scope="s",
                             supported_topics=["t"], must_answer_topics=["t"], tone="x", response_format="y",
                             knowledge_sources=["f.pdf"], acceptance_criteria=["c"])
    with pytest.raises(ValidationError):
        RequirementsDocument(project_name="p", agent_purpose="x", target_audience="a", scope="s",
                             supported_topics=["t"], must_answer_topics=["t"], tone="x", response_format="y",
                             knowledge_sources=[], acceptance_criteria=["c"])


def test_eval_case_consistency():
    with pytest.raises(ValidationError):
        EvalCase(test_id="t1", category="out_of_scope", question="q", expected_behavior="refuse", must_refuse=False)
    with pytest.raises(ValidationError):
        EvalCase(test_id="t1", category="answerable", question="q", expected_behavior="a", expected_facts=[])


def test_retrieval_config_overlap():
    with pytest.raises(ValidationError):
        RetrievalConfig(chunk_size=200, chunk_overlap=300)


def test_agent_answer_coercion():
    a = AgentAnswer.model_validate({"answer": "x", "citations": [{"source": "a.pdf"}], "confidence": 85})
    assert a.citations == ["a.pdf"] and a.confidence == 0.85


def test_local_backend_append_only(tmp_path):
    db = LocalBackend(tmp_path)
    r = db.insert("evaluation_results", {"passed": True})
    with pytest.raises(StorageError):
        db.update("evaluation_results", r["id"], {"passed": False})


def test_repository_approval_gate(tmp_path):
    repo = Repository(LocalBackend(tmp_path))
    agent = AgentDefinition(agent_name="A", project_id="p", run_id="run1", purpose="x",
                            system_prompt="You are a test agent. " * 6, audience="a", tone="t",
                            knowledge_sources=["f"], retrieval_config=RetrievalConfig())
    repo.create_agent(agent)
    with pytest.raises(PermissionError):
        repo.save_agent_version(agent)
