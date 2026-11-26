"""Honest final quality report (Markdown + CSV); numbers come only from measured scorecards."""
from __future__ import annotations

import csv
import io
from collections import Counter

from app.core.schemas import METRICS, AgentDefinition, CaseResult, IterationRecord, Scorecard

METRIC_LABELS = {"grounding": "Grounding", "factual_correctness": "Factual correctness",
                 "citation_correctness": "Citation accuracy", "refusal_correctness": "Refusal accuracy",
                 "scope_adherence": "Scope adherence", "output_contract": "Output contract compliance"}


def pct(x: float | None) -> str:
    return "n/a" if x is None else f"{x * 100:.1f}%"


def honest_summary(final: Scorecard, initial: Scorecard, remaining: Counter, n_iter: int) -> str:
    s = (f"The agent achieved a {pct(final.pass_rate)} evaluation pass rate "
         f"({final.passed_cases} of {final.total_cases} cases).")
    if final.pass_rate == 1.0:
        s += " Every generated test case passed; this does not guarantee correctness on questions outside the dataset."
    if n_iter:
        delta = final.pass_rate - initial.pass_rate
        s += (f" The initial version passed {pct(initial.pass_rate)}; after {n_iter} optimisation "
              f"iteration(s) the kept version {'improved by' if delta > 0 else 'changed by'} {delta * 100:+.1f} points.")
    else:
        s += " No optimisation iteration was run."
    if remaining:
        top = ", ".join(f"{k.replace('_', ' ')} ({v})" for k, v in remaining.most_common(3))
        s += f" Remaining failures were primarily: {top}."
    return s


def results_csv(results: list[CaseResult]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["test_id", "category", "passed", "refused", "failure_categories", *METRICS, "question",
                "answer", "citations"])
    for r in results:
        w.writerow([r.test_id, r.category.value, r.passed, r.answer.refused,
                    ";".join(c.value for c in r.failure_categories),
                    *[(f"{r.metrics[m].score:.2f}" if r.metrics[m].applicable else "n/a") for m in METRICS],
                    r.question, r.answer.answer.replace("\n", " "), ";".join(r.answer.citations)])
    return buf.getvalue()


def final_report_md(*, project_name: str, brief: str, agent: AgentDefinition, initial: Scorecard, final: Scorecard,
                    scorecards: list[Scorecard], iterations: list[IterationRecord], final_results: list[CaseResult],
                    budget: dict, stop_reason: str, groundability_md: str, limitations: list[str],
                    approval: dict, dataset_info: dict) -> str:
    remaining = Counter(c.value for r in final_results if not r.passed for c in r.failure_categories[:1])
    n_iter = len([i for i in iterations if i.to_version])
    L = [f"# Final quality report: {project_name}", "",
         f"**Final agent:** {agent.agent_name} v{agent.version} (model `{agent.model}`)  ",
         f"**Stop reason:** {stop_reason}  ",
         f"**Approved by:** {approval.get('approver')} at {approval.get('timestamp')}", "",
         "## Summary", honest_summary(final, initial, remaining, n_iter), "",
         "## Brief", brief, "",
         "## Headline numbers",
         "Pass rate counts cases that met every pass criterion. Metrics are averaged only over cases where they "
         "apply. The composite score is a separate, derived number.", "",
         "| Measure | Initial (v{}) | Final (v{}) |".format(initial.agent_version, final.agent_version),
         "|---|---|---|",
         f"| Total evaluation cases | {initial.total_cases} | {final.total_cases} |",
         f"| Passed cases | {initial.passed_cases} | {final.passed_cases} |",
         f"| Failed cases | {initial.failed_cases} | {final.failed_cases} |",
         f"| **Case pass rate** | {pct(initial.pass_rate)} | {pct(final.pass_rate)} |"]
    for m in METRICS:
        L.append(f"| {METRIC_LABELS[m]} (n={final.metric_counts.get(m, 0)}) | {pct(initial.metrics.get(m))} | "
                 f"{pct(final.metrics.get(m))} |")
    L += [f"| Composite score | {pct(initial.composite_score)} | {pct(final.composite_score)} |", "",
          f"Composite formula: {final.composite_formula}.", "",
          "## Results by category", "| Category | Passed / total | Pass rate |", "|---|---|---|"]
    for cat, v in final.by_category.items():
        L.append(f"| {cat} | {int(v['passed'])} / {int(v['total'])} | {pct(v['pass_rate'])} |")
    L += ["", "## Optimisation iterations", f"Optimisation iterations run: {n_iter} (maximum 3).", ""]
    L += ["| Iteration | Version | Pass rate before | Pass rate after | Targets | Decision |", "|---|---|---|---|---|---|"]
    for i in iterations:
        L.append(f"| {i.iteration} | v{i.from_version} -> {('v' + str(i.to_version)) if i.to_version else '-'} | "
                 f"{pct(i.score_before)} | {pct(i.score_after)} | {', '.join(i.failure_categories)} | "
                 f"{i.decision}: {i.decision_reason} |")
    for i in iterations:
        if i.changes_made:
            L += ["", f"**Iteration {i.iteration} changes**"] + [f"- {c}" for c in i.changes_made]
            reg = [r for r in i.regression_results if r.get("now") == "fail"]
            fix = [r for r in i.regression_results if r.get("now") == "pass"]
            L.append(f"- Newly passing: {len(fix)}; newly failing (regressions): {len(reg)}")
    L += ["", "## Per-iteration scorecards", "| Eval | Version | Pass rate | Composite |", "|---|---|---|---|"]
    for sc in scorecards:
        L.append(f"| iteration {sc.iteration} | v{sc.agent_version} | {pct(sc.pass_rate)} | {pct(sc.composite_score)} |")
    L += ["", "## Remaining failures (final version)"]
    fails = [r for r in final_results if not r.passed]
    if not fails:
        L.append("None.")
    else:
        L += ["| Test | Category | Failure category | Diagnosis |", "|---|---|---|---|"]
        for r in fails:
            L.append(f"| {r.test_id} | {r.category.value} | {', '.join(c.value for c in r.failure_categories)} | "
                     f"{r.failure_explanation[:160].replace('|', '/')} |")
    L += ["", "## Groundability", groundability_md, "", "## Limitations"] + [f"- {x}" for x in limitations]
    L += ["- Evaluation cases are generated automatically from the same documents; they measure behaviour on this "
          "dataset, not general correctness.",
          "- The LLM judge is a small local model; its scores are combined with deterministic checks and can still "
          "be wrong on individual cases."]
    L += ["", "## Evaluation dataset", f"- Accepted cases: {dataset_info.get('accepted')}",
          f"- Rejected candidates (failed fact verification or scope check): {dataset_info.get('rejected')}",
          f"- Category counts: {dataset_info.get('categories')}", "",
          "## Budget consumed",
          f"- LLM calls: {budget['usage']['llm_calls']} / {budget['limits']['max_llm_calls']}",
          f"- Tokens: {budget['total_tokens']} / {budget['limits']['max_tokens']}",
          f"- Wall-clock time: {budget['usage']['elapsed_seconds'] / 60:.1f} min / "
          f"{budget['limits']['max_seconds'] / 60:.0f} min",
          f"- Calls by stage: {budget['usage']['calls_by_stage']}", ""]
    return "\n".join(L)
