"""Lets the agent plan tool calls and executes only tools attached to its definition."""
from __future__ import annotations

import json

from pydantic import BaseModel, Field

from app.core.llm_service import LLMError, LLMService
from app.core.schemas import AgentDefinition, ToolCall, ToolResult
from app.ingestion.pipeline import KnowledgeBase
from app.tools.registry import ToolBox, ToolContext

MAX_TOOL_CALLS = 3


class _Plan(BaseModel):
    tool_calls: list[ToolCall] = Field(default_factory=list)


PLAN_PROMPT = """You can call tools before answering. Decide which tool calls (if any) are needed to answer
the user's question. Use a tool only if it is clearly needed. Use at most {max_calls} calls.

TOOLS:
{tools}

EVIDENCE ALREADY RETRIEVED (may already contain the answer):
{evidence}

QUESTION: {question}

Return only JSON: {{"tool_calls": [{{"tool": "<name>", "arguments": {{...}}}}]}}  (empty list if none)."""


class ToolExecutor:
    def __init__(self, agent: AgentDefinition):
        ctx = ToolContext(csv_files=[p for p in KnowledgeBase(agent.project_id).csv_files()
                                     if p.name in set(agent.knowledge_sources)])
        self.box = ToolBox(agent.tools, ctx)

    @property
    def active(self) -> bool:
        return bool(self.box.tools)

    def plan_and_run(self, llm: LLMService, question: str, evidence: str, model: str | None) -> list[ToolResult]:
        if not self.active:
            return []
        prompt = PLAN_PROMPT.format(tools=json.dumps(self.box.describe(), indent=1)[:3500],
                                    evidence=evidence[:2500] or "(none)", question=question,
                                    max_calls=MAX_TOOL_CALLS)
        try:
            plan = llm.generate_json([{"role": "user", "content": prompt}], _Plan, stage="runtime_tool_plan",
                                     model=model, max_tokens=400)
        except LLMError as e:
            return [ToolResult(tool="planner", ok=False, error=str(e)[:300])]
        return [self.box.call(c.tool, c.arguments) for c in plan.tool_calls[:MAX_TOOL_CALLS]]
