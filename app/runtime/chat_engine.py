"""Generic agent runtime. Knows nothing about any domain: everything comes from the definition."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field

from app.config import get_settings
from app.core.llm_service import LLMError, LLMService
from app.core.schemas import AgentAnswer, AgentDefinition, EvidenceRef, RuntimeResponse
from app.runtime.output_validator import capture_keys, unsupported_numbers, validate_answer
from app.runtime.retriever import Retriever
from app.runtime.tool_executor import ToolExecutor

HISTORY_TURNS = 3


@dataclass
class ChatSession:
    """Conversation history bound to exactly one agent (and therefore one project)."""
    agent_id: str
    project_id: str
    turns: list[dict] = field(default_factory=list)

    def add(self, question: str, answer: str) -> None:
        self.turns.append({"q": question, "a": answer})
        self.turns = self.turns[-10:]


class AgentRuntime:
    def __init__(self, agent: AgentDefinition, llm: LLMService):
        self.agent = agent
        self.llm = llm
        self.model = agent.model or get_settings().llm_model
        self.retriever = Retriever(agent)
        self.tools = ToolExecutor(agent)

    def new_session(self) -> ChatSession:
        return ChatSession(agent_id=self.agent.agent_id, project_id=self.agent.project_id)

    # ------------------------------------------------------------------
    def ask(self, question: str, session: ChatSession | None = None) -> RuntimeResponse:
        if session and (session.agent_id != self.agent.agent_id or session.project_id != self.agent.project_id):
            raise ValueError("chat session belongs to a different agent/project")
        t0 = time.monotonic()
        calls_before = len(self.llm.call_log)
        a = self.agent
        query = question
        if session and session.turns:
            query = session.turns[-1]["q"] + " " + question  # follow-up questions keep their context
        accepted, all_hits = self.retriever.retrieve(query)
        retrieved = [EvidenceRef(source_filename=h.chunk.source_filename, chunk_id=h.chunk.chunk_id,
                                 location=h.chunk.location, score=h.score, excerpt=h.chunk.text[:400])
                     for h in accepted]
        evidence_block = "\n\n".join(
            f"[{i + 1}] source: {h.chunk.source_filename} ({h.chunk.location})\n{h.chunk.text}"
            for i, h in enumerate(accepted))
        tool_results = self.tools.plan_and_run(self.llm, question, evidence_block, self.model) if self.tools.active else []
        ok_tools = [t for t in tool_results if t.ok]

        def finish(ans: AgentAnswer, valid: bool, errs: list[str], by: str) -> RuntimeResponse:
            return RuntimeResponse(agent_id=a.agent_id, agent_version=a.version, question=question, answer=ans,
                                   retrieved=retrieved, tool_results=tool_results, contract_valid=valid,
                                   contract_errors=errs, refusal_applied_by=by,
                                   latency_s=round(time.monotonic() - t0, 2),
                                   llm_calls=len(self.llm.call_log) - calls_before)

        # deterministic refusal policy: no evidence above threshold and no tool output
        if a.refusal_policy.refuse_when_no_evidence and not accepted and not ok_tools:
            best = max((h.score for h in all_hits), default=0.0)
            ans = AgentAnswer(answer=a.refusal_policy.refusal_message, citations=[], refused=True,
                              refusal_reason=(f"No passage in the approved sources reached the evidence threshold "
                                              f"({best:.2f} < {a.retrieval_config.similarity_threshold})."),
                              confidence=1.0)
            res = finish(ans, True, [], "policy")
            if session:
                session.add(question, ans.answer)
            return res

        tool_block = "\n".join(f"- {t.tool}: {json.dumps(t.output, ensure_ascii=False)[:1500]} (refs: {t.source_refs})"
                               if t.ok else f"- {t.tool} FAILED: {t.error}" for t in tool_results)
        user = [f"QUESTION: {question}", "", "EVIDENCE PASSAGES:", evidence_block or "(no passages above threshold)"]
        if tool_results:
            user += ["", "TOOL RESULTS:", tool_block]
        user += ["", "Answer using only the evidence and tool results. Reply with the JSON object only."]
        messages = [{"role": "system", "content": a.system_prompt}]
        for t in (session.turns[-HISTORY_TURNS:] if session else []):
            messages += [{"role": "user", "content": t["q"]}, {"role": "assistant", "content": t["a"]}]
        messages.append({"role": "user", "content": "\n".join(user)})

        allowed = {h.chunk.source_filename for h in accepted}
        for t in ok_tools:
            allowed |= {r.split(" row ")[0] for r in t.source_refs}
        texts = [h.chunk.text for h in accepted] + [json.dumps(t.output) for t in ok_tools]
        retries = int(a.runtime_options.get("contract_retries", 1))
        errors: list[str] = []
        ans: AgentAnswer | None = None
        for attempt in range(retries + 1):
            keys: dict = {}
            try:
                ans = self.llm.generate_json(messages, AgentAnswer, stage="runtime_answer", model=self.model,
                                             max_tokens=700, post_process=capture_keys(keys))
            except LLMError as e:
                errors = [f"model failed to produce a valid answer: {str(e)[:200]}"]
                ans = AgentAnswer(answer="I could not produce a reliable answer.", refused=True,
                                  refusal_reason="answer generation failed validation", confidence=0.0)
                break
            ans, errors = validate_answer(keys.get("keys", set()), ans, a.output_contract, allowed)
            if a.runtime_options.get("strict_numeric_grounding") and not ans.refused:
                bad = unsupported_numbers(ans.answer, texts, question)
                if bad:
                    errors.append(f"numbers not found in evidence: {sorted(bad)}")
            if not errors or attempt == retries:
                break
            messages = messages + [{"role": "assistant", "content": ans.model_dump_json()},
                                   {"role": "user", "content": "Your reply violated the output contract: "
                                    + "; ".join(errors) + ". Fix it and reply with the JSON object only."}]
        by = "model" if ans.refused else "none"
        res = finish(ans, not errors, errors, by)
        if session:
            session.add(question, ans.answer)
        return res
