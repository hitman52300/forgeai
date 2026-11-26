"""Intake interviewer: understands the brief, inspects the documents, asks <=5 questions."""
from __future__ import annotations

import re

from app.core.llm_service import LLMService, load_prompt, render
from app.core.schemas import ClarifyingQuestion, DocumentRecord, InterviewAnalysis
from app.ingestion.vector_store import VectorStore

MAX_QUESTIONS = 5
# a question whose best matching passage is this similar is treated as answered by the documents
ANSWERED_BY_DOCS_SCORE = 0.62


def document_inventory(docs: list[DocumentRecord], preview_chars: int = 700) -> str:
    lines = []
    for d in docs:
        shape = []
        if d.page_count:
            shape.append(f"{d.page_count} pages")
        if d.row_count is not None:
            shape.append(f"{d.row_count} rows; columns: {', '.join(d.columns or [])}")
        preview = " ".join(d.preview.split())[:preview_chars]
        lines.append(f"- {d.filename} ({d.file_type}, {d.size_bytes} bytes{', ' + '; '.join(shape) if shape else ''})\n"
                     f"  preview: {preview}")
    return "\n".join(lines) if lines else "(no documents uploaded)"


def run_interview(llm: LLMService, brief: str, docs: list[DocumentRecord], store: VectorStore | None,
                  max_questions: int = MAX_QUESTIONS) -> tuple[InterviewAnalysis, list[dict]]:
    """Returns the analysis and a log of questions dropped by the document check."""
    prompt = render(load_prompt("interviewer.txt"), brief=brief, inventory=document_inventory(docs),
                    max_questions=str(max_questions))
    analysis = llm.generate_json([{"role": "user", "content": prompt}], InterviewAnalysis, stage="interview",
                                 max_tokens=1200)
    dropped: list[dict] = []
    kept: list[ClarifyingQuestion] = []
    seen: list[set[str]] = []
    for q in analysis.questions:
        toks = set(re.findall(r"[a-z0-9]+", q.question.lower()))
        if not toks:
            continue
        dup = next((s for s in seen if len(toks & s) / len(toks | s) >= 0.75), None)
        if dup is not None:
            dropped.append({"question": q.question, "reason": "near-duplicate of another question"})
            continue
        seen.append(toks)
        if store is not None and store.count():
            hits = store.query(q.question, 1)
            if hits and hits[0].score >= ANSWERED_BY_DOCS_SCORE:
                dropped.append({"question": q.question, "reason": "answered by documents",
                                "evidence": f"{hits[0].chunk.source_filename} ({hits[0].chunk.location})",
                                "score": hits[0].score})
                continue
        kept.append(q)
    analysis.questions = kept[:max_questions]
    return analysis, dropped


def apply_answers(analysis: InterviewAnalysis, answers: dict[str, str]) -> InterviewAnalysis:
    for q in analysis.questions:
        if q.question_id in answers:
            q.answer = (answers[q.question_id] or "").strip() or None
    return analysis
