"""run_tests tool — delegates ALL command execution to the configured backend.

Unlike legacy ``shellTools.ts`` (child_process.exec on the host), this tool never
spawns a host process itself: the sandbox executor owns execution, limits and
cleanup. Without an executor the tool refuses with an explicit error.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from safefix.models import Observation
from safefix.tools.registry import ToolContext


class RunTestsArgs(BaseModel):
    command: str = Field(description="Test command, e.g. 'python -m pytest -q tests/'")
    timeout: float = Field(default=120.0, gt=0, le=3600)

    @field_validator("command")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("command must not be empty")
        return v


class RunTestsTool:
    name = "run_tests"
    args_model = RunTestsArgs
    description = "Run the project's tests inside the sandbox and return structured output."

    async def execute(self, args: RunTestsArgs, ctx: ToolContext) -> Observation:
        if ctx.executor is None:
            return Observation(
                ok=False,
                error="no execution backend configured; run_tests requires a sandbox executor",
            )
        result = await ctx.executor.run(args.command, cwd=ctx.workspace, timeout=args.timeout)
        return Observation(
            ok=result.exit_code == 0 and not result.timed_out,
            stdout=result.stdout,
            stderr=result.stderr,
            exit_code=result.exit_code,
            error="timeout" if result.timed_out else None,
        )