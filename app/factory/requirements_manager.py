"""Builds the structured requirements document.

Fields that can be derived deterministically (knowledge sources, groundability,
supported / must-refuse topics, tools) are never left to the LLM.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.core.llm_service import LLMService, load_prompt, render
from app.core.schemas import (DocumentRecord, GroundabilityReport, GroundStatus, InterviewAnalysis,
                              RequirementsDocument, ToolSelection)


class _ReqDraft(BaseModel):
    project_name: str = ""
    scope: str
    tone: str = ""
    response_format: str = ""
    must_refuse_topics: list[str] = Field(default_factory=list)
    explicit_limitations: list[str] = Field(default_factory=list)
    unresolved_ambiguities: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)


def _dedupe(items: list[str]) -> list[str]:
    seen, out = set(), []
    for i in items:
        k = " ".join(str(i).lower().split())
        if k and k not in seen:
            seen.add(k)
            out.append(str(i).strip())
    return out


def build_requirements(llm: LLMService, *, project_name: str, brief: str, analysis: InterviewAnalysis,
                       docs: list[DocumentRecord], ground: GroundabilityReport,
                       tools: list[ToolSelection], store=None) -> RequirementsDocument:
    answers = "\n".join(f"Q: {q.question}\nA: {q.answer or '(no answer given)'}" for q in analysis.questions) \
        or "(no clarification questions were needed)"
    supported = ground.by_status(GroundStatus.supported)
    partial = ground.by_status(GroundStatus.partial)
    unsupported = ground.by_status(GroundStatus.unsupported)
    ambiguous = ground.by_status(GroundStatus.ambiguous)
    prompt = render(load_prompt("requirements.txt"), brief=brief,
                    analysis=analysis.model_dump(exclude={"questions"}), answers=answers,
                    sources=", ".join(d.filename for d in docs), supported=supported or "none",
                    partial=partial or "none", unsupported=unsupported or "none", ambiguous=ambiguous or "none")
    draft = llm.generate_json([{"role": "user", "content": prompt}], _ReqDraft, stage="requirements",
                              max_tokens=1200)

    # The LLM may propose extra refuse topics. Keep one only if it is not a supported topic and the
    # documents do not support it (checked with the same groundability guard).
    supported_l = [t.lower() for t in supported + partial]
    extra_refuse, refuse_notes = [], []
    for t in draft.must_refuse_topics[:6]:
        tl = t.lower().strip().strip(".")
        if tl in ("none", "n/a", "na", "nothing", "no", "-"):
            continue
        if not tl or any(tl in s_ or s_ in tl for s_ in supported_l):
            refuse_notes.append(f"dropped proposed refuse topic '{t}': it is a supported topic")
            continue
        if store is not None:
            from app.factory.groundability import check_topic
            g = check_topic(llm, store, t, analysis.agent_purpose)
            if g.status in (GroundStatus.supported, GroundStatus.partial):
                refuse_notes.append(f"dropped proposed refuse topic '{t}': documents support it ({g.status.value})")
                continue
            ground.topics.append(g)
        extra_refuse.append(t)
    limitations = list(draft.explicit_limitations)
    for t in unsupported:
        limitations.append(f"No supporting document for '{t}': the agent must refuse questions about it.")
    for t in partial:
        g = next(x for x in ground.topics if x.topic == t)
        limitations.append(f"'{t}' is only partially covered by the documents. {g.rationale[:200]}")
    ambig = list(draft.unresolved_ambiguities) + [f"Topic '{t}' is ambiguous: "
                                                  f"{next(x for x in ground.topics if x.topic == t).rationale[:160]}"
                                                  for t in ambiguous]
    ambig += [a for a in analysis.ambiguities if not any(q.answer for q in analysis.questions)]
    # LLM criteria that ask to refuse a supported topic contradict groundability and are dropped
    criteria = [c for c in draft.acceptance_criteria
                if not ("refuse" in c.lower() and any(s_ in c.lower() for s_ in supported_l))]
    criteria += [f"Answers questions about '{t}' using the documents." for t in supported]
    criteria += ["Every factual answer cites at least one approved knowledge source.",
                 "Questions outside the approved scope or without document evidence are refused."]
    selected_tools = [t.tool for t in tools if t.selected]
    return RequirementsDocument(
        project_name=project_name or draft.project_name,
        agent_purpose=analysis.agent_purpose,
        target_audience=analysis.target_audience,
        scope=draft.scope,
        supported_topics=supported + partial,
        must_answer_topics=supported,
        must_refuse_topics=_dedupe(unsupported + extra_refuse),
        tone=draft.tone or analysis.tone or "professional and concise",
        response_format=draft.response_format or analysis.response_format or "short paragraphs with citations",
        required_tools=selected_tools,
        knowledge_sources=[d.filename for d in docs if d.status == "ingested"],
        explicit_limitations=_dedupe(limitations),
        unresolved_ambiguities=_dedupe(ambig),
        groundability_findings=ground.topics,
        acceptance_criteria=_dedupe(criteria),
        decision_notes=refuse_notes,
    )


def requirements_markdown(r: RequirementsDocument, tool_reasons: list[ToolSelection] | None = None) -> str:
    def bl(items):
        return "\n".join(f"- {i}" for i in items) if items else "- (none)"
    from app.factory.groundability import matrix_markdown
    out = [f"# Requirements: {r.project_name}", "", f"**Purpose:** {r.agent_purpose}",
           f"**Audience:** {r.target_audience}", f"**Scope:** {r.scope}", f"**Tone:** {r.tone}",
           f"**Response format:** {r.response_format}", "", "## Supported topics", bl(r.supported_topics),
           "## Must-answer topics", bl(r.must_answer_topics), "## Must-refuse topics", bl(r.must_refuse_topics),
           "## Required tools", bl(r.required_tools)]
    if tool_reasons:
        out += ["", "Tool decisions:", bl([f"{t.tool}: {'attached' if t.selected else 'not attached'} — {t.reason}"
                                         for t in tool_reasons])]
    out += ["## Knowledge sources", bl(r.knowledge_sources), "## Explicit limitations", bl(r.explicit_limitations),
            "## Unresolved ambiguities", bl(r.unresolved_ambiguities), "## Groundability matrix",
            matrix_markdown(GroundabilityReport(topics=r.groundability_findings)), "",
            "## Acceptance criteria", bl(r.acceptance_criteria)]
    if r.decision_notes:
        out += ["", "## Factory decision notes", bl(r.decision_notes)]
    return "\n".join(out) + "\n"
