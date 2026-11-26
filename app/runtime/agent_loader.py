"""Load and validate any agent definition (file, dict or repository)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.core.schemas import AgentDefinition
from app.tools.registry import all_tools


class AgentLoadError(ValueError):
    pass


def load_agent(source: str | Path | dict[str, Any]) -> AgentDefinition:
    if isinstance(source, (str, Path)):
        p = Path(source)
        if not p.exists():
            raise AgentLoadError(f"agent definition not found: {p}")
        data = json.loads(p.read_text(encoding="utf-8"))
    else:
        data = source
    try:
        agent = AgentDefinition.model_validate(data)
    except Exception as e:  # noqa: BLE001
        raise AgentLoadError(f"invalid agent definition: {e}") from e
    unknown = [t for t in agent.tools if t not in all_tools()]
    if unknown:
        raise AgentLoadError(f"agent references tools that are not in the registry: {unknown}")
    return agent


def save_agent(agent: AgentDefinition, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(agent.model_dump_json(indent=2), encoding="utf-8")
    return path
