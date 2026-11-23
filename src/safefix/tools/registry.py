"""Tool registry — upgraded port of legacy ``tools/tool.ts``.

Upgrades: every tool declares a Pydantic argument model; dispatch validates
arguments in STRICT mode before execution (no int->str coercion surprises), and
unknown tools / malformed arguments are rejected without ever executing.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, ValidationError

from safefix.models import Action, Observation
from safefix.runtime.executor import ExecutionBackend


@dataclass
class ToolContext:
    workspace: Path
    executor: ExecutionBackend | None = None


class Tool(Protocol):
    name: str
    args_model: type[BaseModel]
    description: str

    async def execute(self, args: BaseModel, ctx: ToolContext) -> Observation: ...


class ToolRegistry:
    def __init__(self, tools: list[Tool]):
        self._tools = {t.name: t for t in tools}

    def tools(self) -> list[Tool]:
        return list(self._tools.values())

    def schemas(self) -> list[dict]:
        """OpenAI-style function schemas for native tool calling."""
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": getattr(t, "description", t.name),
                    "parameters": t.args_model.model_json_schema(),
                },
            }
            for t in self._tools.values()
        ]

    async def dispatch(self, action: Action, ctx: ToolContext) -> Observation:
        tool = self._tools.get(action.tool)
        if tool is None:
            return Observation(ok=False, error=f"unknown tool: {action.tool}")
        try:
            args = tool.args_model.model_validate(action.args, strict=True)
        except ValidationError as e:
            return Observation(ok=False, error=f"invalid arguments for {action.tool}: {e}")
        try:
            return await tool.execute(args, ctx)
        except Exception as e:  # containment: a broken tool must not crash the loop
            return Observation(ok=False, error=str(e) or type(e).__name__)
