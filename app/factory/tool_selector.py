"""Decides which registry tools an agent needs.

LLM decision based on the requirements + each tool's generic selection hint,
followed by deterministic availability rules (e.g. csv_lookup requires a CSV
knowledge source). No demo names or filenames are involved.
"""
from __future__ import annotations

from pydantic import BaseModel

from app.core.llm_service import LLMService, load_prompt, render
from app.core.schemas import ToolSelection
from app.tools.registry import ToolContext, all_tools


class _Selections(BaseModel):
    selections: list[ToolSelection]


def select_tools(llm: LLMService, *, purpose: str, scope: str, topics: list[str], source_types: list[str],
                 notes: str, ctx: ToolContext) -> list[ToolSelection]:
    tools = all_tools()
    desc = "\n".join(f"- {t.name}: {t.description} When needed: {t.selection_hint}" for t in tools.values())
    prompt = render(load_prompt("tool_selector.txt"), purpose=purpose, scope=scope, topics=", ".join(topics),
                    source_types=", ".join(sorted(set(source_types))), notes=notes or "(none)", tools=desc)
    out = llm.generate_json([{"role": "user", "content": prompt}], _Selections, stage="tool_selection",
                            max_tokens=600)
    by_name = {s.tool: s for s in out.selections if s.tool in tools}
    final: list[ToolSelection] = []
    for name, tool in tools.items():
        s = by_name.get(name) or ToolSelection(tool=name, selected=False, reason="not selected by the analysis")
        ok, why = tool.available(ctx)
        if s.selected and not ok:
            s = ToolSelection(tool=name, selected=False, reason=f"deselected: {why}")
        final.append(s)
    return final
