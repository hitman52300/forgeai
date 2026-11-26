"""Targeted, logged changes to an agent definition (see prompts/optimizer.txt)."""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

from app.core.llm_service import LLMService
from app.core.schemas import (AgentDefinition, CaseResult, EvalDataset, FailureCategory, RequirementsDocument,
                              utcnow)
from app.factory.agent_generator import PromptParts, assemble_system_prompt
from app.optimization.critic import critique

CONTRACT_RULE = ("Always reply with the complete JSON object containing answer, citations, refused, "
                 "refusal_reason and confidence; never add text outside the JSON.")


@dataclass
class Change:
    field_path: str
    old: Any
    new: Any
    reason: str


@dataclass
class OptimizationPlan:
    targets: list[str]
    changes: list[Change] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    rejected_rules: list[str] = field(default_factory=list)
    affected_test_ids: list[str] = field(default_factory=list)


def _failed(results: list[CaseResult], cat: FailureCategory) -> list[CaseResult]:
    return [r for r in results if not r.passed and r.failure_categories and r.failure_categories[0] == cat]


def optimize(llm: LLMService, agent: AgentDefinition, req: RequirementsDocument, results: list[CaseResult],
             dataset: EvalDataset, targets: list[FailureCategory], iteration: int) -> tuple[AgentDefinition, OptimizationPlan]:
    new = agent.model_copy(deep=True)
    plan = OptimizationPlan(targets=[t.value for t in targets])
    rc = new.retrieval_config

    def change(path: str, old: Any, val: Any, reason: str) -> None:
        if old != val:
            plan.changes.append(Change(path, copy.deepcopy(old), copy.deepcopy(val), reason))

    for cat in targets:
        failed = _failed(results, cat)
        plan.affected_test_ids += [r.test_id for r in failed]
        n = len(failed)
        if cat == FailureCategory.retrieval_miss:
            if rc.top_k < 9:
                old = rc.top_k
                rc.top_k = min(12, rc.top_k + 3)
                change("retrieval_config.top_k", old, rc.top_k, f"{n} retrieval misses: retrieve more passages")
                old_t = rc.similarity_threshold
                rc.similarity_threshold = round(max(0.10, rc.similarity_threshold - 0.05), 3)
                change("retrieval_config.similarity_threshold", old_t, rc.similarity_threshold,
                       "admit slightly less similar passages that contained the expected facts")
            else:
                old_c, old_o = rc.chunk_size, rc.chunk_overlap
                rc.chunk_size = max(300, int(rc.chunk_size * 0.7))
                rc.chunk_overlap = int(rc.chunk_size * 0.15)
                rc.collection_name = ""
                change("retrieval_config.chunk_size", old_c, rc.chunk_size,
                       f"{n} retrieval misses persisted after raising top_k: use finer chunks")
                change("retrieval_config.chunk_overlap", old_o, rc.chunk_overlap, "keep 15% overlap")
            plan.reasons.append(f"retrieval_miss x{n}: relevant passages were not retrieved")
        elif cat == FailureCategory.output_contract:
            old = new.runtime_options.get("contract_retries", 1)
            new.runtime_options["contract_retries"] = min(3, old + 1)
            change("runtime_options.contract_retries", old, new.runtime_options["contract_retries"],
                   f"{n} output-contract violations: allow a validated retry")
            if CONTRACT_RULE not in new.extra_rules:
                change("extra_rules", list(new.extra_rules), new.extra_rules + [CONTRACT_RULE], "schema reminder")
                new.extra_rules.append(CONTRACT_RULE)
            plan.reasons.append(f"output_contract_defect x{n}")
        elif cat == FailureCategory.tool_defect:
            if "calculator" not in new.tools and any("calculator" in r.failure_explanation or
                                                      "calcul" in r.question.lower() for r in failed):
                change("tools", list(new.tools), new.tools + ["calculator"],
                       "calculation questions failed without a deterministic calculator")
                new.tools.append("calculator")
            rule = "For any arithmetic, call the calculator tool with the numbers from the evidence instead of computing mentally."
            if "calculator" in new.tools and rule not in new.extra_rules:
                change("extra_rules", list(new.extra_rules), new.extra_rules + [rule], "tool usage rule")
                new.extra_rules.append(rule)
            plan.reasons.append(f"tool_defect x{n}")
        else:
            if cat == FailureCategory.hallucination and not new.runtime_options.get("strict_numeric_grounding"):
                change("runtime_options.strict_numeric_grounding", False, True,
                       f"{n} hallucinations: validate that numbers in answers exist in the evidence")
                new.runtime_options["strict_numeric_grounding"] = True
            if cat == FailureCategory.wrong_refusal:
                answered_oos = sum(1 for r in failed if r.deterministic_checks.get("must_refuse"))
                refused_ok = n - answered_oos
                old_t = rc.similarity_threshold
                step = 0.05 if answered_oos > refused_ok else -0.05
                rc.similarity_threshold = round(min(0.6, max(0.10, rc.similarity_threshold + step)), 3)
                new.refusal_policy.min_evidence_score = rc.similarity_threshold
                change("retrieval_config.similarity_threshold", old_t, rc.similarity_threshold,
                       f"wrong refusals: {answered_oos} answered-but-should-refuse vs {refused_ok} "
                       f"refused-but-should-answer")
            root, rules, rejected = critique(llm, new, cat, failed, dataset)
            plan.rejected_rules += rejected
            if rules:
                change("extra_rules", list(new.extra_rules), new.extra_rules + rules,
                       f"critic ({cat.value}): {root[:200]}")
                new.extra_rules += rules
            plan.reasons.append(f"{cat.value} x{n}: {root[:200]}")

    # re-assemble the prompt from its structured parts so only the changed section differs
    if new.prompt_parts:
        parts = PromptParts.model_validate(new.prompt_parts)
        new.system_prompt = assemble_system_prompt(parts, req, new.refusal_policy, new.output_contract,
                                                   new.extra_rules)
    new.version = agent.version + 1
    new.parent_version = agent.version
    new.created_at = utcnow()
    new.change_summary = [f"{c.field_path}: {c.old!r} -> {c.new!r} ({c.reason})" for c in plan.changes] or \
        ["no applicable change"]
    plan.affected_test_ids = sorted(set(plan.affected_test_ids))
    return new, plan
