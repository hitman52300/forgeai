"""Groundability guard: semantic retrieval + LLM analysis of the retrieved evidence.

Combination rule (explainable):
1. If no passage reaches `min_score`, the topic is UNSUPPORTED without asking the LLM.
2. Otherwise the LLM judges each retrieved passage: does it contain concrete facts
   about the topic? (per-passage yes/no is more reliable for small models than a
   single holistic label). Ids not in the retrieved set are discarded.
3. SUPPORTED   = >=2 fact-bearing passages with similarity >= `strong_score`, or one
                 such passage and no missing aspects reported.
   PARTIAL     = fact-bearing passages exist but fewer/weaker than above.
   AMBIGUOUS   = fact-bearing passages contradict each other.
   UNSUPPORTED = no fact-bearing passage.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.core.llm_service import LLMService, load_prompt, render
from app.core.schemas import EvidenceRef, GroundabilityReport, GroundStatus, TopicGroundability
from app.ingestion.vector_store import VectorStore


class _PassageVerdict(BaseModel):
    id: str
    has_facts: bool
    reason: str = ""


class _Verdict(BaseModel):
    passages: list[_PassageVerdict] = Field(default_factory=list)
    contradiction: bool = False
    missing_aspects: list[str] = Field(default_factory=list)
    rationale: str = ""


def check_topic(llm: LLMService, store: VectorStore, topic: str, purpose: str, *, top_k: int = 6,
                min_score: float = 0.25, strong_score: float = 0.38) -> TopicGroundability:
    hits = {}
    for q in (topic, f"{topic} — {purpose}"):
        for h in store.query(q, top_k):
            if h.chunk.chunk_id not in hits or hits[h.chunk.chunk_id].score < h.score:
                hits[h.chunk.chunk_id] = h
    ranked = sorted(hits.values(), key=lambda h: h.score, reverse=True)[:top_k]
    best = ranked[0].score if ranked else 0.0
    refs = {f"E{i + 1}": h for i, h in enumerate(ranked)}

    def ev(h) -> EvidenceRef:
        return EvidenceRef(source_filename=h.chunk.source_filename, chunk_id=h.chunk.chunk_id,
                           location=h.chunk.location, score=h.score, excerpt=h.chunk.text[:300])

    if best < min_score:
        return TopicGroundability(topic=topic, status=GroundStatus.unsupported, retrieval_max_score=best,
                                  evidence=[ev(h) for h in ranked[:2]],
                                  rationale=f"No passage reached the retrieval threshold ({best:.2f} < {min_score}).")
    evidence_txt = "\n\n".join(f"[{rid}] ({h.chunk.source_filename}, {h.chunk.location}, similarity {h.score:.2f})\n"
                               f"{h.chunk.text[:900]}" for rid, h in refs.items())
    prompt = render(load_prompt("groundability.txt"), topic=topic, purpose=purpose, evidence=evidence_txt)
    v = llm.generate_json([{"role": "user", "content": prompt}], _Verdict, stage="groundability", max_tokens=600)
    valid_ids = [p.id.strip().strip("[]") for p in v.passages
                 if p.has_facts and p.id.strip().strip("[]") in refs]
    strong = [i for i in valid_ids if refs[i].score >= strong_score]
    notes = []
    if v.contradiction and valid_ids:
        status = GroundStatus.ambiguous
        notes.append("passages contradict each other")
    elif len(strong) >= 2 or (strong and not v.missing_aspects):
        status = GroundStatus.supported
    elif valid_ids:
        status = GroundStatus.partial
        if not strong:
            notes.append(f"supporting passages are weak matches (best {best:.2f} < {strong_score})")
    else:
        status = GroundStatus.unsupported
        notes.append("no retrieved passage contains concrete facts about the topic")
    llm_status = GroundStatus.supported if valid_ids else GroundStatus.unsupported
    evidence = [ev(refs[i]) for i in valid_ids] or [ev(h) for h in ranked[:2]]
    rationale = v.rationale.strip()
    rationale += f" {len(valid_ids)} of {len(refs)} retrieved passages contain usable facts."
    if v.missing_aspects:
        rationale += f" Missing: {', '.join(v.missing_aspects[:4])}."
    if notes:
        rationale += " [" + "; ".join(notes) + "]"
    return TopicGroundability(topic=topic, status=status, evidence=evidence, rationale=rationale.strip(),
                              retrieval_max_score=best, llm_status=llm_status)


def assess(llm: LLMService, store: VectorStore, topics: list[str], purpose: str, **kw) -> GroundabilityReport:
    seen, results = set(), []
    for t in topics:
        k = t.strip().lower()
        if k and k not in seen:
            seen.add(k)
            results.append(check_topic(llm, store, t.strip(), purpose, **kw))
    return GroundabilityReport(topics=results)


def matrix_markdown(report: GroundabilityReport) -> str:
    rows = ["| Requested topic | Evidence | Status | Best similarity |", "|---|---|---|---|"]
    for t in report.topics:
        ev = ", ".join(sorted({f"{e.source_filename} ({e.location})" for e in t.evidence[:3]})) \
            if t.status != GroundStatus.unsupported else "No supporting document"
        rows.append(f"| {t.topic} | {ev} | {t.status.value} | {t.retrieval_max_score:.2f} |")
    return "\n".join(rows)
