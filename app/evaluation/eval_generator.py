"""Automatic evaluation dataset generation, grounded in the indexed documents.

Every expected fact is verified deterministically against the source chunk it
was generated from (normalised substring or high token recall with all numbers
present). Candidates that fail verification are rejected and kept in the
dataset's `rejected_candidates` for transparency. Out-of-scope candidates are
rejected if retrieval finds strong evidence for them.
"""
from __future__ import annotations

import random
import re
from dataclasses import dataclass

from pydantic import BaseModel, Field

from app.core.budget_manager import BudgetExceeded
from app.core.llm_service import LLMError, LLMService, load_prompt, render
from app.core.schemas import Chunk, EvalCase, EvalCategory, EvalDataset, RequirementsDocument
from app.ingestion.vector_store import VectorStore
from app.runtime.output_validator import numbers_in

_W = re.compile(r"[a-z0-9]+(?:\.[0-9]+)?")
STOP = set("a an the of to and or in on for with by is are be as at from that this it its was were will can "
           "may must should any all each per not no".split())


def norm(s: str) -> str:
    return " ".join(_W.findall(s.lower()))


def content_tokens(s: str) -> list[str]:
    return [t for t in _W.findall(s.lower()) if t not in STOP]


def verify_fact(fact: str, source_text: str) -> dict:
    """A fact is traceable if it appears (normalised) in the source, or if >=85% of its
    content words and ALL of its numbers appear in the source."""
    nf, ns = norm(fact), norm(source_text)
    if not nf:
        return {"fact": fact, "verified": False, "method": "empty"}
    if nf in ns:
        return {"fact": fact, "verified": True, "method": "substring"}
    toks = content_tokens(fact)
    src = set(content_tokens(source_text))
    recall = sum(t in src for t in toks) / len(toks) if toks else 0.0
    nums_ok = numbers_in(fact) <= numbers_in(source_text)
    ok = recall >= 0.85 and nums_ok and len(toks) >= 2
    return {"fact": fact, "verified": ok, "method": "token_recall", "recall": round(recall, 2),
            "numbers_ok": nums_ok}


class _Single(BaseModel):
    question: str
    expected_facts: list[str] = Field(default_factory=list)
    difficulty: str = "medium"
    rationale: str = ""


class _Multi(BaseModel):
    possible: bool = True
    question: str = ""
    facts_from_a: list[str] = Field(default_factory=list)
    facts_from_b: list[str] = Field(default_factory=list)
    rationale: str = ""


class _Edge(BaseModel):
    question: str
    correct_facts: list[str] = Field(default_factory=list)
    expected_behavior: str = ""
    difficulty: str = "hard"
    rationale: str = ""


class _OOSItem(BaseModel):
    question: str
    reason: str = ""
    kind: str = "outside_scope"


class _OOS(BaseModel):
    questions: list[_OOSItem]


EDGE_TYPES = {
    "false_premise": ("Write a question that assumes something the passage CONTRADICTS (e.g. a wrong value, "
                      "a wrong condition). correct_facts must be the passage's actual information."),
    "ambiguous": ("Write a vague question related to the passage's subject that could mean several things "
                  "and cannot be answered precisely without clarification. correct_facts must be empty."),
    "incomplete": ("Write a question that is missing a key detail needed to answer it (e.g. which case, which "
                   "item, which category), so a good answer asks for the detail or covers the options."),
    "paraphrased": ("Write a question that the passage answers, but phrased very differently from the "
                    "passage's wording (synonyms, informal tone, indirect phrasing)."),
    "partial_information": ("Write a question that the passage only PARTLY answers: one part is covered, "
                            "another closely related part is not in the passage. correct_facts = the covered part."),
}
EDGE_BEHAVIOR = {
    "false_premise": "Point out that the assumption is incorrect and give the correct information with a citation.",
    "ambiguous": "Ask a clarifying question or explain the possible interpretations instead of guessing.",
    "incomplete": "Ask for the missing detail or answer for the documented cases, without guessing.",
    "paraphrased": "Answer correctly from the documents despite the different wording, with a citation.",
    "partial_information": "Answer the covered part with a citation and state that the rest is not in the documents.",
}


@dataclass
class GenConfig:
    target_cases: int = 30
    seed: int = 7
    answerable_share: float = 0.45
    out_of_scope_share: float = 0.25
    oos_max_similarity: float = 0.55
    min_chunk_chars: int = 160


class EvalGenerator:
    def __init__(self, llm: LLMService, store: VectorStore, req: RequirementsDocument, cfg: GenConfig):
        self.llm, self.store, self.req, self.cfg = llm, store, req, cfg
        self.rng = random.Random(cfg.seed)
        self.rejected: list[dict] = []
        self.cases: list[EvalCase] = []
        self._n = 0

    # ---------------------------------------------------------------- helpers
    def _id(self, prefix: str) -> str:
        self._n += 1
        return f"{prefix}-{self._n:03d}"

    def _ask(self, prompt: str, schema, stage: str):
        return self.llm.generate_json([{"role": "user", "content": prompt}], schema, stage=stage,
                                      temperature=0.0, max_tokens=700)

    def _sample_chunks(self, n: int) -> list[Chunk]:
        chunks = [c for c in self.store.all_chunks() if len(c.text) >= self.cfg.min_chunk_chars]
        by_doc: dict[str, list[Chunk]] = {}
        for c in chunks:
            by_doc.setdefault(c.source_filename, []).append(c)
        for lst in by_doc.values():
            self.rng.shuffle(lst)
        order: list[Chunk] = []
        docs = sorted(by_doc)
        while len(order) < n and any(by_doc.values()):
            for d in docs:  # round-robin across documents so every source is tested
                if by_doc[d]:
                    order.append(by_doc[d].pop())
        return order[:n]

    def _verified(self, facts: list[str], source: str) -> tuple[list[str], list[dict]]:
        checks = [verify_fact(f, source) for f in facts if f and f.strip()]
        return [c["fact"] for c in checks if c["verified"]], checks

    # ---------------------------------------------------------------- generators
    def answerable(self, chunk: Chunk, style: str) -> EvalCase | None:
        p = render(load_prompt("eval_generator.txt"), purpose=self.req.agent_purpose,
                   audience=self.req.target_audience, style=style, source=chunk.source_filename,
                   passage=chunk.text[:1800])
        out = self._ask(p, _Single, "eval_generation")
        facts, checks = self._verified(out.expected_facts, chunk.text)
        if not facts or not out.question.strip():
            self.rejected.append({"type": "answerable", "question": out.question, "source": chunk.chunk_id,
                                  "reason": "no expected fact could be traced to the source", "checks": checks})
            return None
        return EvalCase(test_id=self._id("ANS"), category=EvalCategory.answerable, subtype="single_document",
                        question=out.question.strip(), expected_behavior="Answer correctly with a citation.",
                        expected_sources=[chunk.source_filename], expected_facts=facts, must_refuse=False,
                        difficulty=out.difficulty if out.difficulty in ("easy", "medium", "hard") else "medium",
                        evaluation_rationale=out.rationale[:400], evidence_chunk_ids=[chunk.chunk_id],
                        fact_verification=checks)

    def multi(self, a: Chunk) -> EvalCase | None:
        partner = None
        for h in self.store.query(a.text[:600], 8):
            if h.chunk.source_filename != a.source_filename and h.score >= 0.3:
                partner = h.chunk
                break
        if partner is None:
            for h in self.store.query(a.text[:600], 8):
                if h.chunk.chunk_id != a.chunk_id and abs(h.chunk.chunk_index - a.chunk_index) > 1 and h.score >= 0.35:
                    partner = h.chunk
                    break
        if partner is None:
            self.rejected.append({"type": "multi", "source": a.chunk_id, "reason": "no related second passage"})
            return None
        p = render(load_prompt("eval_generator_multi.txt"), purpose=self.req.agent_purpose,
                   source_a=a.source_filename, passage_a=a.text[:1400], source_b=partner.source_filename,
                   passage_b=partner.text[:1400])
        out = self._ask(p, _Multi, "eval_generation")
        fa, ca = self._verified(out.facts_from_a, a.text)
        fb, cb = self._verified(out.facts_from_b, partner.text)
        if not out.possible or not out.question.strip() or not fa or not fb:
            self.rejected.append({"type": "multi", "question": out.question, "sources": [a.chunk_id, partner.chunk_id],
                                  "reason": "not possible or facts not traceable to both passages",
                                  "checks": ca + cb})
            return None
        srcs = sorted({a.source_filename, partner.source_filename})
        return EvalCase(test_id=self._id("MUL"), category=EvalCategory.answerable,
                        subtype="multi_document" if len(srcs) > 1 else "multi_evidence",
                        question=out.question.strip(),
                        expected_behavior="Combine evidence from both sources and cite them.",
                        expected_sources=srcs, expected_facts=fa + fb, difficulty="hard",
                        evaluation_rationale=out.rationale[:400], evidence_chunk_ids=[a.chunk_id, partner.chunk_id],
                        fact_verification=ca + cb)

    def edge(self, chunk: Chunk, edge_type: str) -> EvalCase | None:
        p = render(load_prompt("eval_generator_edge.txt"), purpose=self.req.agent_purpose, edge_type=edge_type,
                   type_instructions=EDGE_TYPES[edge_type], source=chunk.source_filename, passage=chunk.text[:1800])
        out = self._ask(p, _Edge, "eval_generation")
        facts, checks = self._verified(out.correct_facts, chunk.text)
        needs_facts = edge_type in ("false_premise", "paraphrased", "partial_information")
        if not out.question.strip() or (needs_facts and not facts):
            self.rejected.append({"type": edge_type, "question": out.question, "source": chunk.chunk_id,
                                  "reason": "required correct facts not traceable to the source", "checks": checks})
            return None
        if edge_type in ("ambiguous", "incomplete"):
            facts = []
        return EvalCase(test_id=self._id("EDG"), category=EvalCategory.edge_case, subtype=edge_type,
                        question=out.question.strip(), expected_behavior=EDGE_BEHAVIOR[edge_type],
                        expected_sources=[chunk.source_filename] if facts else [],
                        expected_facts=facts, must_refuse=False,
                        difficulty="hard" if out.difficulty == "hard" else "medium",
                        evaluation_rationale=out.rationale[:400], evidence_chunk_ids=[chunk.chunk_id],
                        fact_verification=checks)

    def out_of_scope(self, n: int) -> list[EvalCase]:
        p = render(load_prompt("eval_generator_out_of_scope.txt"), purpose=self.req.agent_purpose,
                   scope=self.req.scope, supported=", ".join(self.req.supported_topics),
                   refuse_topics=", ".join(self.req.must_refuse_topics) or "none", n=str(n + 3))
        out = self._ask(p, _OOS, "eval_generation")
        cases = []
        for item in out.questions:
            if len(cases) >= n:
                break
            hits = self.store.query(item.question, 1)
            best = hits[0].score if hits else 0.0
            if best >= self.cfg.oos_max_similarity:
                self.rejected.append({"type": "out_of_scope", "question": item.question, "best_similarity": best,
                                      "reason": "documents contain strongly related evidence; may be answerable"})
                continue
            cases.append(EvalCase(test_id=self._id("OOS"), category=EvalCategory.out_of_scope,
                                  subtype=item.kind, question=item.question.strip(),
                                  expected_behavior="Refuse: the approved sources do not support an answer.",
                                  must_refuse=True, difficulty="easy" if item.kind == "outside_scope" else "medium",
                                  evaluation_rationale=f"{item.reason} (best retrieval similarity {best:.2f})"))
        return cases

    # ---------------------------------------------------------------- main
    def generate(self, run_id: str) -> EvalDataset:
        t = self.cfg.target_cases
        n_ans = round(t * self.cfg.answerable_share)
        n_multi = max(2, round(n_ans * 0.25))
        n_single = n_ans - n_multi
        n_oos = round(t * self.cfg.out_of_scope_share)
        n_edge = t - n_ans - n_oos
        pool = self._sample_chunks(n_single + n_multi + n_edge + 20)
        styles = ["direct factual question", "question about a specific condition or exception",
                  "question asking for a specific value, limit or duration", "how-to / procedure question"]
        it = iter(pool)
        try:
            produced = 0
            for chunk in it:
                if produced >= n_single:
                    break
                c = self.answerable(chunk, styles[produced % len(styles)])
                if c:
                    self.cases.append(c)
                    produced += 1
            produced = 0
            for chunk in it:
                if produced >= n_multi:
                    break
                c = self.multi(chunk)
                if c:
                    self.cases.append(c)
                    produced += 1
            edge_order = list(EDGE_TYPES)
            produced = 0
            for chunk in it:
                if produced >= n_edge:
                    break
                c = self.edge(chunk, edge_order[produced % len(edge_order)])
                if c:
                    self.cases.append(c)
                    produced += 1
            # top up answerable cases if the chunk pool ran short elsewhere
            self.cases += self.out_of_scope(n_oos)
        except (LLMError, BudgetExceeded) as e:
            self.rejected.append({"type": "generation_stopped", "reason": str(e)[:300]})
        return EvalDataset(run_id=run_id, cases=self.cases, rejected_candidates=self.rejected,
                           generation_config={"target_cases": t, "seed": self.cfg.seed, "temperature": 0.0,
                                              "planned": {"single": n_single, "multi": n_multi, "edge": n_edge,
                                                          "out_of_scope": n_oos},
                                              "prompts": ["eval_generator.txt", "eval_generator_multi.txt",
                                                          "eval_generator_edge.txt",
                                                          "eval_generator_out_of_scope.txt"]})
