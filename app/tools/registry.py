"""Controlled tool registry.

Each tool exposes a name, description, input/output schema (Pydantic), an
execution function, error handling and permission/availability information.
A generated agent can only call tools that are listed in its definition: the
runtime builds a `ToolBox` from that list and nothing else.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel, ValidationError

from app.core.schemas import ToolResult, ToolSpec


@dataclass
class ToolContext:
    csv_files: list[Path] = field(default_factory=list)
    network_allowed: bool = True


class BaseTool:
    name: str = ""
    description: str = ""
    selection_hint: str = ""  # generic description of when the tool is needed (used by the tool selector)
    input_model: type[BaseModel]
    output_model: type[BaseModel]
    requires_network: bool = False
    requires_csv_source: bool = False
    permission: str = "read_only"

    def spec(self) -> ToolSpec:
        return ToolSpec(name=self.name, description=self.description,
                        input_schema=self.input_model.model_json_schema(),
                        output_schema=self.output_model.model_json_schema(),
                        requires_network=self.requires_network, requires_csv_source=self.requires_csv_source,
                        permission="network_read_only" if self.requires_network else "read_only")

    def available(self, ctx: ToolContext) -> tuple[bool, str]:
        if self.requires_csv_source and not ctx.csv_files:
            return False, "no CSV knowledge source is attached"
        if self.requires_network and not ctx.network_allowed:
            return False, "network access disabled"
        return True, ""

    def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        ok, why = self.available(ctx)
        if not ok:
            return ToolResult(tool=self.name, ok=False, error=f"tool unavailable: {why}")
        try:
            inp = self.input_model.model_validate(args or {})
        except ValidationError as e:
            return ToolResult(tool=self.name, ok=False, error=f"invalid arguments: {e.errors()[:3]}")
        try:
            out, refs = self.execute(inp, ctx)
            out = self.output_model.model_validate(out)
        except ToolError as e:
            return ToolResult(tool=self.name, ok=False, error=str(e))
        except ValidationError as e:
            return ToolResult(tool=self.name, ok=False, error=f"tool produced invalid output: {e.errors()[:2]}")
        except Exception as e:  # noqa: BLE001
            return ToolResult(tool=self.name, ok=False, error=f"{type(e).__name__}: {e}")
        return ToolResult(tool=self.name, ok=True, output=out.model_dump(), source_refs=refs)

    def execute(self, inp: Any, ctx: ToolContext) -> tuple[dict, list[str]]:
        raise NotImplementedError


class ToolError(RuntimeError):
    pass


_REGISTRY: dict[str, Callable[[], BaseTool]] = {}


def register(factory: Callable[[], BaseTool]) -> Callable[[], BaseTool]:
    tool = factory()
    _REGISTRY[tool.name] = factory
    return factory


def all_tools() -> dict[str, BaseTool]:
    _load_builtin()
    return {name: f() for name, f in _REGISTRY.items()}


def get_tool(name: str) -> BaseTool:
    tools = all_tools()
    if name not in tools:
        raise KeyError(f"tool '{name}' is not in the registry")
    return tools[name]


def _load_builtin() -> None:
    from app.tools import calculator, csv_lookup, current_date, weather_api  # noqa: F401


class ToolBox:
    """The only tools a given agent may call."""

    def __init__(self, names: list[str], ctx: ToolContext):
        registry = all_tools()
        unknown = [n for n in names if n not in registry]
        if unknown:
            raise KeyError(f"agent references unknown tools: {unknown}")
        self.tools = {n: registry[n] for n in names}
        self.ctx = ctx

    def call(self, name: str, args: dict[str, Any]) -> ToolResult:
        if name not in self.tools:
            return ToolResult(tool=name, ok=False, error=f"tool '{name}' is not attached to this agent")
        return self.tools[name].run(args, self.ctx)

    def describe(self) -> list[dict]:
        return [{"name": t.name, "description": t.description, "input_schema": t.input_model.model_json_schema()}
                for t in self.tools.values()]
