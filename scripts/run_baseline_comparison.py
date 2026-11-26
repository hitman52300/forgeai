"""Bonus A: factory agent vs manually engineered baseline, same dataset / documents / rubric / conditions.

    python scripts/run_baseline_comparison.py <factory_run_id> baseline/hr_human_baseline.json

Both agents are (re-)evaluated in the same session with the same LLM settings, judge
model and evaluation dataset. A balanced pairwise judgement (both answer orders,
only consistent verdicts counted) is added for answerable cases.
"""
from __future__ import annotations

import json
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.core.budget_manager import BudgetManager  # noqa: E402
from app.core.llm_service import LLMService  # noqa: E402
from app.core.orchestrator import Factory  # noqa: E402
from app.core.schemas import METRICS, AgentDefinition, BudgetLimits, EvalDataset  # noqa: E402
from app.evaluation.evaluator import evaluate, results_to_json  # noqa: E402
from app.evaluation.llm_judge import pairwise_preference  # noqa: E402
from app.evaluation.scorecard import build_scorecard  # noqa: E402
from app.ingestion.pipeline import KnowledgeBase  # noqa: E402
from app.reporting.artifact_manager import ArtifactManager  # noqa: E402
from app.reporting.report_generator import METRIC_LABELS, pct  # noqa: E402


def main(run_id: str, baseline_path: str) -> None:
    f = Factory()
    run, am = f.load(run_id)
    factory_agent = AgentDefinition.model_validate(am.read_json("agent_definition_final.json"))
    ds = EvalDataset.model_validate(am.read_json("evaluation_dataset.json"))
    raw = Path(baseline_path).read_text(encoding="utf-8").replace("{{PROJECT_ID}}", run.project_id)
    baseline = AgentDefinition.model_validate(json.loads(raw))
    baseline.retrieval_config.collection_name = KnowledgeBase(run.project_id).ensure_index(baseline.retrieval_config)
    try:
        f.repo.create_agent(baseline, origin="human_baseline")
        f.repo.save_agent_version(baseline)
        f.repo.set_final_version(baseline.agent_id, baseline.version)
    except Exception as e:  # noqa: BLE001  (already registered on a re-run)
        print("baseline registration:", str(e)[:120])
    bam = ArtifactManager(f"{am.slug}/baseline_comparison", run.project_id, run_id, f.repo)
    bam.write_text("human_baseline_agent.json", baseline.model_dump_json(indent=2))

    budget = BudgetManager(BudgetLimits(max_llm_calls=len(ds.cases) * 10 + 50, max_seconds=4 * 3600))
    llm = LLMService.from_settings(budget=budget)
    say = lambda i, n, t: print(f"  {t} {i}/{n}", flush=True)  # noqa: E731
    out = {}
    for label, agent in (("forgeai", factory_agent), ("human_baseline", baseline)):
        t0 = time.time()
        res = evaluate(agent, llm, llm, ds, iteration=0, progress=say)
        sc = build_scorecard(run_id, res, agent.version, 0, label=label)
        out[label] = {"results": res, "scorecard": sc, "eval_seconds": round(time.time() - t0, 1)}
        bam.write_json(f"evaluation_results_{label}.json", results_to_json(res))
        f.repo.save_scorecard(sc)

    # balanced pairwise comparison on answerable + edge cases
    fr = {r.test_id: r for r in out["forgeai"]["results"]}
    hr = {r.test_id: r for r in out["human_baseline"]["results"]}
    pair = []
    for i, c in enumerate([c for c in ds.cases if not c.must_refuse]):
        a, b = fr[c.test_id], hr[c.test_id]
        ev = "\n".join(e.excerpt for e in a.retrieved[:4])
        p = pairwise_preference(llm, c.question, ev, a.answer.answer, b.answer.answer, seed=i)
        pair.append({"test_id": c.test_id, **p})
    wins = Counter({"x": "forgeai", "y": "human_baseline"}.get(p["winner"], p["winner"]) for p in pair)

    # creation effort
    st = am.read_json("run_state.json")["run"]
    budget_f = am.read_json("budget.json")
    iters = am.read_json("iteration_logs.json") or []
    comp = {
        "dataset_cases": len(ds.cases), "same_conditions": {
            "dataset": "evaluation_dataset.json of the factory run", "documents": factory_agent.knowledge_sources,
            "rubric": "app/evaluation/evaluator.py + prompts/judge.txt", "agent_model": factory_agent.model,
            "judge_model": llm.settings.judge_model, "evaluated_in_same_session": True},
        "agents": {k: {"scorecard": v["scorecard"].model_dump(), "eval_seconds": v["eval_seconds"]}
                   for k, v in out.items()},
        "pairwise_balanced": {"counts": dict(wins), "cases": pair},
        "creation_effort": {
            "forgeai": {"factory_wall_clock_minutes": round(budget_f["usage"]["elapsed_seconds"] / 60, 1),
                        "llm_calls": budget_f["usage"]["llm_calls"],
                        "human_inputs": "brief + interview answers + one approval",
                        "automatic_versions": 1 + len([i for i in iters if i.get("to_version")])},
            "human_baseline": {"authoring": "single manual pass (system prompt, retrieval settings, refusal list)",
                               "manual_changes_after_first_version": 0,
                               "note": "written by the developer's AI coding assistant acting as the manual "
                                       "engineer; human minutes were not measured"}},
        "budget_used_for_comparison": budget.snapshot(),
    }
    bam.write_json("baseline_comparison.json", comp)
    f.repo.save_baseline(run_id, factory_agent.version, baseline.agent_name,
                         {k: v["scorecard"].model_dump() for k, v in out.items()} | {"pairwise": dict(wins)})
    F, H = out["forgeai"]["scorecard"], out["human_baseline"]["scorecard"]
    md = ["# ForgeAI vs manual baseline", "",
          f"Dataset: {len(ds.cases)} cases from the factory run (same documents, rubric, agent model "
          f"`{factory_agent.model}`, judge `{llm.settings.judge_model}`). Both agents were evaluated in the same session.",
          "", "| Measure | ForgeAI v{} | Manual baseline |".format(factory_agent.version), "|---|---|---|",
          f"| Case pass rate | {pct(F.pass_rate)} | {pct(H.pass_rate)} |",
          f"| Failed cases | {F.failed_cases} | {H.failed_cases} |"]
    for m in METRICS:
        md.append(f"| {METRIC_LABELS[m]} | {pct(F.metrics[m])} | {pct(H.metrics[m])} |")
    md += [f"| Composite | {pct(F.composite_score)} | {pct(H.composite_score)} |", "",
           "## Results by category", "| Category | ForgeAI | Manual |", "|---|---|---|"]
    for cat in F.by_category:
        md.append(f"| {cat} | {pct(F.by_category[cat]['pass_rate'])} | {pct(H.by_category.get(cat, {}).get('pass_rate'))} |")
    md += ["", "## Balanced pairwise judgement (non-refusal cases)",
           f"Each pair judged in both orders; only consistent verdicts count. Result: {dict(wins)}", "",
           "## Failure categories", f"- ForgeAI: {F.failure_categories}", f"- Manual: {H.failure_categories}", "",
           "## Creation effort", f"- ForgeAI: {comp['creation_effort']['forgeai']}",
           f"- Manual: {comp['creation_effort']['human_baseline']}", "",
           "## Where each approach did better",
           "_Filled in from the numbers above in docs/FINAL_PROJECT_REPORT; no number here was edited by hand._", ""]
    bam.write_text("baseline_comparison.md", "\n".join(md))
    print("\n".join(md))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
