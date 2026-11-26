"""Critic–optimizer loop: at most three optimisation iterations after the initial evaluation."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable

from app.core.budget_manager import BudgetExceeded, BudgetManager
from app.core.llm_service import LLMService
from app.core.schemas import (AgentDefinition, CaseResult, EvalDataset, IterationRecord, RequirementsDocument,
                              Scorecard)
from app.evaluation.evaluator import evaluate
from app.evaluation.scorecard import build_scorecard
from app.optimization.critic import choose_targets
from app.optimization.optimizer import optimize

log = logging.getLogger("forgeai.optimizer")
MIN_IMPROVEMENT = 0.01  # pass-rate points below which an iteration counts as "no measurable improvement"


@dataclass
class LoopOutcome:
    versions: list[AgentDefinition]
    results: dict[int, list[CaseResult]]       # iteration -> results
    scorecards: list[Scorecard]
    iterations: list[IterationRecord]
    best_version: int
    stop_reason: str
    change_log: list[dict] = field(default_factory=list)


def _key(sc: Scorecard) -> tuple[float, float]:
    return (sc.pass_rate, sc.composite_score)


def run_loop(*, run_id: str, agent: AgentDefinition, req: RequirementsDocument, dataset: EvalDataset,
             agent_llm: LLMService, judge_llm: LLMService, budget: BudgetManager, quality_target: float,
             max_iterations: int = 3, on_version: Callable[[AgentDefinition], None] | None = None,
             on_eval: Callable[[int, list[CaseResult], Scorecard], None] | None = None,
             on_iteration: Callable[[IterationRecord, list[dict]], None] | None = None,
             progress: Callable[[str], None] | None = None) -> LoopOutcome:
    max_iterations = min(3, max_iterations)
    say = progress or (lambda m: None)

    say("evaluating initial agent")
    res0 = evaluate(agent, agent_llm, judge_llm, dataset, iteration=0,
                    progress=lambda i, n, t: say(f"initial evaluation {i}/{n} ({t})"))
    sc0 = build_scorecard(run_id, res0, agent.version, 0)
    if on_eval:
        on_eval(0, res0, sc0)
    out = LoopOutcome(versions=[agent], results={0: res0}, scorecards=[sc0], iterations=[],
                      best_version=agent.version, stop_reason="")
    best_agent, best_sc, best_res = agent, sc0, res0
    current, cur_sc, cur_res = agent, sc0, res0
    calls_per_eval = max(1, sum(v for k, v in budget.usage.calls_by_stage.items()
                                if k in ("runtime_answer", "runtime_tool_plan", "judge")))
    tried_without_gain: set = set()

    for it in range(1, max_iterations + 1):
        if best_sc.pass_rate >= quality_target:
            out.stop_reason = f"quality target reached (pass rate {best_sc.pass_rate:.0%} >= {quality_target:.0%})"
            break
        if cur_sc.failed_cases == 0:
            out.stop_reason = "no failing cases"
            break
        ok, why = budget.can_afford(calls_per_eval + 4)
        if not ok:
            out.stop_reason = f"budget: {why}"
            break
        targets = choose_targets(cur_res, exclude=tried_without_gain)
        if not targets:
            out.stop_reason = "no remaining failure category has an applicable fix"
            break
        say(f"iteration {it}: fixing {[t.value for t in targets]}")
        try:
            new, plan = optimize(agent_llm, current, req, cur_res, dataset, targets, it)
        except BudgetExceeded as e:
            out.stop_reason = f"budget: {e.reason}"
            break
        if not plan.changes:
            tried_without_gain |= set(targets)
            rec = IterationRecord(iteration=it, from_version=current.version, to_version=None,
                                  score_before=cur_sc.pass_rate, score_after=None, pass_rate_before=cur_sc.pass_rate,
                                  failure_categories=[t.value for t in targets], changes_made=[],
                                  reason_for_changes=plan.reasons + plan.rejected_rules,
                                  affected_test_ids=plan.affected_test_ids, decision="continue",
                                  decision_reason="no applicable change for these categories; trying others")
            out.iterations.append(rec)
            if on_iteration:
                on_iteration(rec, [])
            continue
        if on_version:
            on_version(new)
        out.versions.append(new)
        try:
            res = evaluate(new, agent_llm, judge_llm, dataset, iteration=it,
                           progress=lambda i, n, t: say(f"iteration {it} evaluation {i}/{n} ({t})"))
        except BudgetExceeded as e:
            out.stop_reason = f"budget exhausted during iteration {it} evaluation: {e.reason}"
            break
        budget.record_iteration()
        sc = build_scorecard(run_id, res, new.version, it)
        if on_eval:
            on_eval(it, res, sc)
        before = {r.test_id: r.passed for r in cur_res}
        regressions = [{"test_id": r.test_id, "was": "pass", "now": "fail",
                        "categories": [c.value for c in r.failure_categories]}
                       for r in res if before.get(r.test_id) and not r.passed]
        fixed = [r.test_id for r in res if not before.get(r.test_id, True) and r.passed]
        gain = sc.pass_rate - cur_sc.pass_rate
        improved = _key(sc) > _key(best_sc) and (gain >= MIN_IMPROVEMENT or sc.composite_score > best_sc.composite_score)
        if improved:
            best_agent, best_sc, best_res = new, sc, res
        else:
            tried_without_gain |= set(targets)
        reached = best_sc.pass_rate >= quality_target
        last = it == max_iterations
        if reached:
            decision, reason = "stop", "quality target reached"
        elif not improved and gain < MIN_IMPROVEMENT:
            decision, reason = "stop", f"no measurable improvement (pass rate change {gain:+.1%})"
        elif last:
            decision, reason = "stop", "maximum of three optimisation iterations completed"
        else:
            decision, reason = "continue", f"improved by {gain:+.1%}; failures remain"
        rec = IterationRecord(
            iteration=it, from_version=current.version, to_version=new.version, score_before=cur_sc.pass_rate,
            score_after=sc.pass_rate, pass_rate_before=cur_sc.pass_rate, pass_rate_after=sc.pass_rate,
            failure_categories=[t.value for t in targets],
            changes_made=[f"{c.field_path}: {c.old!r} -> {c.new!r}" for c in plan.changes],
            reason_for_changes=[c.reason for c in plan.changes] + plan.reasons + plan.rejected_rules,
            affected_test_ids=plan.affected_test_ids,
            regression_results=regressions + [{"test_id": t, "was": "fail", "now": "pass"} for t in fixed],
            decision=decision, decision_reason=reason, kept_version=best_agent.version)
        out.iterations.append(rec)
        changes = [{"iteration": it, "version": new.version, "field_path": c.field_path, "old": c.old,
                    "new": c.new, "reason": c.reason} for c in plan.changes]
        out.change_log += changes
        if on_iteration:
            on_iteration(rec, changes)
        out.results[it] = res
        out.scorecards.append(sc)
        # continue from the best version so a regression is not built upon
        current, cur_sc, cur_res = best_agent, best_sc, best_res
        if decision == "stop":
            out.stop_reason = reason
            break
    else:
        out.stop_reason = out.stop_reason or "maximum of three optimisation iterations completed"
    if not out.stop_reason:
        out.stop_reason = "maximum of three optimisation iterations completed"
    out.best_version = best_agent.version
    return out
