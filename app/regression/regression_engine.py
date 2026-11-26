"""Regression mode: re-test a delivered agent after its document collection changes.

1. detect added / removed / modified documents by content hash (document_versions)
2. re-ingest only what changed, in every index of the project
3. keep the previous evaluation dataset unchanged
4. run the previous tests against the agent on the updated documents
5. compare with the previous results; separate agent regressions from tests whose
   expected facts are no longer present in the documents ("stale tests")
6. write a regression report into a new folder (old results are never replaced)
"""
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone

from app.core.budget_manager import BudgetManager
from app.core.llm_service import LLMService
from app.core.schemas import AgentDefinition, BudgetLimits, CaseResult, EvalDataset, RetrievalConfig
from app.evaluation.eval_generator import verify_fact
from app.evaluation.evaluator import evaluate, results_to_json
from app.evaluation.scorecard import build_scorecard
from app.ingestion.pipeline import KnowledgeBase
from app.ingestion.vector_store import VectorStore
from app.reporting.artifact_manager import ArtifactManager
from app.reporting.report_generator import pct


def run_regression(factory, base_run_id: str, files: list[tuple[str, bytes]], label: str | None = None,
                   progress=None) -> dict:
    say = progress or (lambda m: None)
    run, am = factory.load(base_run_id)
    if run.status != "completed":
        raise ValueError("regression mode needs a completed base run")
    final = AgentDefinition.model_validate(am.read_json("agent_definition_final.json"))
    dataset = EvalDataset.model_validate(am.read_json("evaluation_dataset.json"))
    old_results = [CaseResult.model_validate(r) for r in am.read_json("evaluation_results_final.json")]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    sub = f"regression_{label or stamp}"
    ram = ArtifactManager(f"{am.slug}/{sub}", run.project_id, base_run_id, factory.repo)

    say("detecting document changes")
    kb = KnowledgeBase(run.project_id, factory.repo)
    before = {k: v["hash"] for k, v in kb.documents().items()}
    rep = kb.ingest(files, RetrievalConfig(), sync_removed=True)   # base index; other indexes synced inside
    kb.ensure_index(final.retrieval_config)
    changes = [c for c in rep.changes if c["change_type"] != "unchanged"]
    ram.write_json("document_changes.json", {"before_hashes": before, "changes": rep.changes, "errors": rep.errors})

    # which old tests are still traceable to the updated documents?
    store = VectorStore(final.retrieval_config.collection_name or kb.ensure_index(final.retrieval_config))
    all_text = "\n".join(c.text for c in store.all_chunks())
    stale = {}
    for c in dataset.cases:
        lost = [f for f in c.expected_facts if not verify_fact(f, all_text)["verified"]]
        if lost:
            stale[c.test_id] = lost

    say("re-running previous evaluation dataset")
    budget = BudgetManager(BudgetLimits(max_llm_calls=len(dataset.cases) * 4 + 20))
    llm = LLMService.from_settings(factory.s, budget)
    new_results = evaluate(final, llm, llm, dataset, iteration=0,
                           progress=lambda i, n, t: say(f"regression {i}/{n} ({t})"))
    old_sc = build_scorecard(base_run_id, old_results, final.version, 0, label="before_change")
    new_sc = build_scorecard(base_run_id, new_results, final.version, 0, label="after_change")
    old_by = {r.test_id: r for r in old_results}
    comparison = []
    for r in new_results:
        o = old_by.get(r.test_id)
        status = ("still_pass" if o and o.passed and r.passed else "still_fail" if o and not o.passed and not r.passed
                  else "newly_failing" if o and o.passed else "newly_passing")
        comparison.append({"test_id": r.test_id, "status": status, "stale_test": r.test_id in stale,
                           "facts_no_longer_in_documents": stale.get(r.test_id, []),
                           "old_answer": o.answer.answer[:300] if o else None, "new_answer": r.answer.answer[:300],
                           "new_failure_categories": [c.value for c in r.failure_categories]})
    counts = Counter(c["status"] for c in comparison)
    regressions = [c for c in comparison if c["status"] == "newly_failing" and not c["stale_test"]]
    summary = {"base_run_id": base_run_id, "agent_version": final.version, "document_changes": changes,
               "tests": len(comparison), "status_counts": dict(counts), "stale_tests": len(stale),
               "agent_regressions": len(regressions),
               "pass_rate_before": old_sc.pass_rate, "pass_rate_after": new_sc.pass_rate,
               "llm_calls": budget.usage.llm_calls}
    ram.write_json("evaluation_results_after_change.json", results_to_json(new_results))
    ram.write_json("scorecards.json", [old_sc.model_dump(), new_sc.model_dump()])
    ram.write_json("regression_report.json", {"summary": summary, "comparison": comparison})
    md = ["# Regression report", "", f"Base run: `{base_run_id}`; agent v{final.version}; created {stamp}", "",
          "## Document changes"] + [f"- {c['filename']}: {c['change_type']}" for c in changes] + [
          "", "## Result", f"- Pass rate before change: {pct(old_sc.pass_rate)}",
          f"- Pass rate after change: {pct(new_sc.pass_rate)}",
          f"- Newly failing: {counts.get('newly_failing', 0)} (of which caused by documents no longer containing "
          f"the expected facts: {counts.get('newly_failing', 0) - len(regressions)})",
          f"- Newly passing: {counts.get('newly_passing', 0)}",
          f"- Tests whose expected facts are no longer in the documents (stale): {len(stale)}", "",
          "## Newly failing tests", "| Test | Stale test? | Categories | New answer |", "|---|---|---|---|"]
    for c in comparison:
        if c["status"] == "newly_failing":
            md.append(f"| {c['test_id']} | {'yes' if c['stale_test'] else 'no'} | "
                      f"{', '.join(c['new_failure_categories'])} | {c['new_answer'][:120].replace('|', '/')} |")
    md += ["", "Old evaluation results were not modified; this report lives in its own folder."]
    ram.write_text("regression_report.md", "\n".join(md) + "\n")
    factory.repo.save_regression(run.project_id, base_run_id, changes, summary, {"comparison": comparison})
    factory.repo.audit("regression_run", project_id=run.project_id, run_id=base_run_id, actor_label="factory",
                       details=summary)
    return {"folder": str(ram.dir), **summary}
