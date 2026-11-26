"""Aggregates case results into a scorecard.  Pass rate, individual metrics and the
composite score are reported separately and never conflated."""
from __future__ import annotations

from collections import Counter

from app.core.schemas import METRICS, CaseResult, Scorecard

COMPOSITE_FORMULA = ("composite = mean of the six metric averages (grounding, factual_correctness, "
                     "citation_correctness, refusal_correctness, scope_adherence, output_contract), each "
                     "averaged only over cases where it applies")


def build_scorecard(run_id: str, results: list[CaseResult], agent_version: int, iteration: int,
                    label: str = "factory") -> Scorecard:
    total = len(results)
    passed = sum(r.passed for r in results)
    metrics, counts = {}, {}
    for m in METRICS:
        vals = [r.metrics[m].score for r in results if m in r.metrics and r.metrics[m].applicable]
        counts[m] = len(vals)
        metrics[m] = round(sum(vals) / len(vals), 4) if vals else 0.0
    applicable = [metrics[m] for m in METRICS if counts[m]]
    composite = round(sum(applicable) / len(applicable), 4) if applicable else 0.0
    by_cat: dict[str, dict[str, float]] = {}
    for cat in sorted({r.category.value for r in results}):
        rs = [r for r in results if r.category.value == cat]
        by_cat[cat] = {"total": len(rs), "passed": sum(r.passed for r in rs),
                       "pass_rate": round(sum(r.passed for r in rs) / len(rs), 4)}
    fails = Counter(c.value for r in results if not r.passed for c in r.failure_categories)
    return Scorecard(run_id=run_id, agent_version=agent_version, iteration=iteration, label=label,
                     total_cases=total, passed_cases=passed, failed_cases=total - passed,
                     pass_rate=round(passed / total, 4) if total else 0.0, metrics=metrics, metric_counts=counts,
                     composite_score=composite, composite_formula=COMPOSITE_FORMULA, by_category=by_cat,
                     failure_categories=dict(fails))
