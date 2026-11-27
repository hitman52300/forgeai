"""Generates the declarative, versioned agent definition from approved requirements.

The LLM writes the identity / boundary / style parts of the system prompt;
grounding, citation, refusal and output-format sections are assembled from
fixed templates so they are always present and testable. Retrieval settings
are derived from measured document characteristics.
"""
from __future__ import annotations

import statistics

from pydantic import BaseModel, Field

from app.core.llm_service import LLMService, load_prompt, render
from app.core.schemas import (MIN_EVAL_CASES, AgentDefinition, DocumentRecord, OutputContract, RefusalPolicy, RequirementsDocument,
                              RetrievalConfig)
from app.ingestion.vector_store import VectorStore


class PromptParts(BaseModel):
    agent_name: str
    identity: str
    objective: str
    knowledge_boundaries: list[str] = Field(default_factory=list)
    ambiguity_rules: list[str] = Field(default_factory=list)
    style_rules: list[str] = Field(default_factory=list)
    tool_rules: list[str] = Field(default_factory=list)


GROUNDING_RULES = [
    "Answer ONLY from the numbered evidence passages and tool results provided with each question.",
    "Never use outside knowledge, assumptions or typical industry practice to fill gaps.",
    "If the evidence covers only part of the question, answer that part and state clearly what is not covered.",
    "Never claim to have performed an action (sending, booking, ordering, updating records). You can only provide information.",
]
CITATION_RULES = [
    "Put the source filename of every passage you used in the `citations` list, exactly as written in the evidence header.",
    "Cite only passages you actually used. Never cite a file that does not appear in the evidence.",
]


def assemble_system_prompt(parts: PromptParts, req: RequirementsDocument, refusal: RefusalPolicy,
                           contract: OutputContract, extra_rules: list[str] | None = None) -> str:
    def bl(xs):
        return "\n".join(f"- {x}" for x in xs if x and str(x).strip())
    refuse_topics = ", ".join(refusal.refuse_topics) or "none listed"
    sections = [
        f"# Identity\n{parts.identity.strip()}",
        f"# Objective\n{parts.objective.strip()}\nAudience: {req.target_audience}.",
        f"# Knowledge boundaries\n{bl(parts.knowledge_boundaries)}\n- Supported topics: {', '.join(req.supported_topics)}.\n"
        f"- Approved knowledge sources: {', '.join(req.knowledge_sources)}.",
        f"# Grounding\n{bl(GROUNDING_RULES)}",
        f"# Citations\n{bl(CITATION_RULES)}\n- Citation format: {contract.citation_format}.",
        "# Refusal\n" + bl([
            f"Refuse questions about these topics: {refuse_topics}.",
            "Refuse when the evidence does not contain the answer. Do not guess.",
            "Similar topics are not enough: if the question asks for a specific fact (a person's records, statistics, "
            "history, future plans, prices or dates) that is not written in the passages, refuse instead of answering "
            "a related question.",
            f"When refusing: set refused=true, give the reason in refusal_reason, and use an answer like: \"{refusal.refusal_message}\"",
        ]),
        "# Ambiguity and false assumptions\n" + bl(parts.ambiguity_rules + [
            "If a question contains an assumption that the evidence contradicts, say so and give the correct information from the evidence.",
            "If a question is too vague to answer reliably, set needs_clarification=true and ask one short clarifying question in `answer`.",
        ]),
        f"# Style\n{bl(parts.style_rules)}\n- Tone: {req.tone}.\n- Format of the answer text: {req.response_format}.\n"
        f"- Keep the answer under {contract.max_answer_words} words.",
    ]
    if parts.tool_rules:
        sections.append(f"# Tools\n{bl(parts.tool_rules)}")
    if extra_rules:
        sections.append(f"# Additional rules\n{bl(extra_rules)}")
    sections.append(
        "# Output format\nReply with ONE JSON object and nothing else:\n"
        '{"answer": "<text>", "citations": ["<source filename>", ...], "refused": false, '
        '"refusal_reason": "", "confidence": 0.0-1.0, "needs_clarification": false}\n'
        f"Required fields: {', '.join(contract.required_fields)}. {contract.uncertainty_handling}")
    return "\n\n".join(sections)


def derive_retrieval_config(docs: list[DocumentRecord], store: VectorStore | None, base: RetrievalConfig) -> RetrievalConfig:
    """Choose chunking/top-k from measured document characteristics (no domain assumptions)."""
    prose_lengths = []
    if store is not None and store.count():
        prose_lengths = [len(c.text) for c in store.all_chunks() if c.content_type == "prose"]
    n_docs = len([d for d in docs if d.status == "ingested"])
    has_table = any(d.file_type == "csv" for d in docs)
    median = statistics.median(prose_lengths) if prose_lengths else base.chunk_size
    total_chars = sum(prose_lengths)
    if total_chars and total_chars < 15000:
        chunk = 600
    elif median < 500:
        chunk = 600
    else:
        chunk = 800
    if total_chars > 120000:
        chunk = 1000
    overlap = int(chunk * 0.15)
    top_k = min(8, 4 + max(0, n_docs - 2) + (1 if has_table else 0))
    reasons = [f"{n_docs} documents, {total_chars} prose characters, median indexed chunk {int(median)} chars",
               f"chunk_size={chunk} overlap={overlap} (15%)",
               f"top_k={top_k} (more documents/tables need more passages for cross-document questions)"]
    return RetrievalConfig(chunk_size=chunk, chunk_overlap=overlap, separators=base.separators, top_k=top_k,
                           similarity_threshold=0.25, rationale="; ".join(reasons))


def generate_agent(llm: LLMService, *, req: RequirementsDocument, project_id: str, run_id: str,
                   retrieval: RetrievalConfig, model: str) -> AgentDefinition:
    prompt = render(load_prompt("agent_generator.txt"),
                    requirements=req.model_dump(exclude={"groundability_findings"}),
                    tools=", ".join(req.required_tools) or "none")
    parts = llm.generate_json([{"role": "user", "content": prompt}], PromptParts, stage="agent_generation",
                              max_tokens=1200)
    refusal = RefusalPolicy(refuse_topics=req.must_refuse_topics, refuse_when_no_evidence=True,
                            min_evidence_score=retrieval.similarity_threshold)
    contract = OutputContract()
    system_prompt = assemble_system_prompt(parts, req, refusal, contract)
    return _build(parts, req, project_id, run_id, retrieval, refusal, contract, system_prompt, model)


def _build(parts, req, project_id, run_id, retrieval, refusal, contract, system_prompt, model) -> AgentDefinition:
    d = AgentDefinition(
        agent_name=parts.agent_name.strip()[:80] or req.project_name,
        version=1, project_id=project_id, run_id=run_id, purpose=req.agent_purpose,
        system_prompt=system_prompt, audience=req.target_audience, tone=req.tone,
        knowledge_sources=req.knowledge_sources, supported_topics=req.supported_topics,
        retrieval_config=retrieval, tools=req.required_tools, output_contract=contract, refusal_policy=refusal,
        limitations=req.explicit_limitations,
        evaluation_requirements={"min_cases": MIN_EVAL_CASES, "acceptance_criteria": req.acceptance_criteria,
                                 "categories": ["answerable", "out_of_scope", "edge_case"]},
        model=model, change_summary=["initial version generated from approved requirements"],
        prompt_parts=parts.model_dump(), extra_rules=[],
    )
    return d
