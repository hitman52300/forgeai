"""Run a generated agent on its own, without the factory, API or UI.

    python scripts/run_agent.py artifacts/agents/<agent_id>/final.json
    python scripts/run_agent.py <definition.json> --question "How many days of annual leave do I get?"
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.core.llm_service import LLMService  # noqa: E402
from app.runtime.agent_loader import load_agent  # noqa: E402
from app.runtime.chat_engine import AgentRuntime  # noqa: E402


def show(r) -> None:
    a = r.answer
    print(f"\n{a.answer}")
    if a.citations:
        print(f"  sources: {', '.join(a.citations)}")
    if a.refused:
        print(f"  refused ({r.refusal_applied_by}): {a.refusal_reason}")
    if not r.contract_valid:
        print(f"  contract issues: {r.contract_errors}")
    print(f"  [{r.latency_s:.1f}s, {len(r.retrieved)} passages, tools: {[t.tool for t in r.tool_results]}]")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("definition")
    ap.add_argument("--question")
    a = ap.parse_args()
    agent = load_agent(a.definition)
    rt = AgentRuntime(agent, LLMService.from_settings())
    print(f"{agent.agent_name} v{agent.version} · tools: {agent.tools or 'none'} · sources: {agent.knowledge_sources}")
    if a.question:
        show(rt.ask(a.question))
        return
    session = rt.new_session()
    while True:
        try:
            q = input("\nyou> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if q.lower() in ("exit", "quit"):
            break
        if q:
            show(rt.ask(q, session))


if __name__ == "__main__":
    main()
