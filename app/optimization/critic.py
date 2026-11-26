"""Critic: groups failures, chooses targets and asks the LLM for general prompt rules."""
from __future__ import annotations

from collections import Counter

from pydantic import BaseModel, Field

from app.core.llm_service import LLMError, LLMService, load_prompt, render
from app.core.schemas import AgentDefinition, CaseResult, EvalDataset, FailureCategory
from app.evaluation.eval_generator import norm
from app.runtime.output_validator import numbers_in

PRIORITY = [FailureCategory.output_contract, FailureCategory.retrieval_miss, FailureCategory.hallucination,
            FailureCategory.wrong_refusal, FailureCategory.tool_defect, FailureCategory.prompt_defect]

MEANING = {
    FailureCategory.retrieval_miss: "the relevant information exists but was not retrieved",
    FailureCategory.prompt_defect: "the evidence was available but the assistant answered incompletely, "
                                   "cited badly or handled an ambiguous/false-premise question poorly",
    FailureCategory.hallucination: "the assistant stated information that is not in the evidence",
    FailureCategory.wrong_refusal: "the assistant refused a supported question or answered one it must refuse",
    FailureCategory.tool_defect: "a needed tool was missing or used incorrectly",
    FailureCategory.output_contract: "the reply did not follow the required JSON output contract",
}


class _Critique(BaseModel):
    root_cause: str = ""
    rules: list[str] = Field(default_factory=list)


def failure_counts(results: list[CaseResult]) -> Counter:
    return Counter(c for r in results if not r.passed for c in r.failure_categories[:1])


def choose_targets(results: list[CaseResult], max_targets: int = 2,
                   exclude: set[FailureCategory] | None = None) -> list[FailureCategory]:
    counts = failure_counts(results)
    cats = [c for c in counts if not exclude or c not in exclude]
    cats.sort(key=lambda c: (-counts[c], PRIORITY.index(c)))
    return cats[:max_targets]


def leaks(rule: str, dataset: EvalDataset) -> bool:
    nr = norm(rule)
    rule_nums = numbers_in(rule)
    for c in dataset.cases:
        for f in c.expected_facts:
            nf = norm(f)
            if len(nf) > 8 and nf in nr:
                return True
            if numbers_in(f) & rule_nums:
                return True
    return False


def critique(llm: LLMService, agent: AgentDefinition, category: FailureCategory, failed: list[CaseResult],
             dataset: EvalDataset) -> tuple[str, list[str], list[str]]:
    """Returns (root cause, accepted rules, rejected rules with reason)."""
    examples = []
    for r in failed[:4]:
        case = next(c for c in dataset.cases if c.test_id == r.test_id)
        examples.append(f"- question: {r.question}\n  expected behaviour: {case.expected_behavior}\n"
                        f"  assistant answer: {r.answer.answer[:300]} (refused={r.answer.refused}, "
                        f"citations={r.answer.citations})\n  diagnosis: {r.failure_explanation[:250]}")
    rules_txt = "\n".join(f"- {x}" for x in (agent.extra_rules or [])) or "(no additional rules yet)"
    prompt = render(load_prompt("critic.txt"), category=category.value, category_meaning=MEANING[category],
                    rules=rules_txt, examples="\n".join(examples))
    try:
        out = llm.generate_json([{"role": "user", "content": prompt}], _Critique, stage="critic",
                                temperature=0.0, max_tokens=400)
    except LLMError as e:
        return f"critic unavailable: {e}", [], []
    accepted, rejected = [], []
    existing = {norm(x) for x in agent.extra_rules}
    for rule in out.rules[:2]:
        rule = rule.strip()
        if not rule or norm(rule) in existing:
            continue
        if leaks(rule, dataset):
            rejected.append(f"{rule}  [rejected: contains an expected fact/number from the test set]")
        elif len(rule.split()) > 60:
            rejected.append(f"{rule}  [rejected: too long]")
        else:
            accepted.append(rule)
    return out.root_cause, accepted, rejected
