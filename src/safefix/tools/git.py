"""git_status / git_diff — trusted fixed-argv git calls on the disposable workspace.

No model-controlled shell string is involved: argv is constant, only the cwd is
the isolated task copy. Host git is a product dependency (repository management),
not an untrusted-execution path.
"""

from __future__ import annotations

import asyncio

from pydantic import BaseModel

from safefix.models import Observation
from safefix.tools.registry import ToolContext


class GitArgs(BaseModel):
    pass


async def _git(workspace, *args: str) -> tuple[int, str, str]:
    proc = await asyncio.create_subprocess_exec(
        "git",
        *args,
        cwd=workspace,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=30)
    except TimeoutError:
        proc.kill()
        await proc.wait()
        return -1, "", "git command timed out"
    return proc.returncode or 0, out.decode("utf-8", "replace"), err.decode("utf-8", "replace")


class GitStatusTool:
    name = "git_status"
    args_model = GitArgs
    description = "Show working-tree status (porcelain) of the task workspace."

    async def execute(self, args: GitArgs, ctx: ToolContext) -> Observation:
        rc, out, err = await _git(ctx.workspace, "status", "--porcelain")
        if rc != 0:
            return Observation(ok=False, error=err.strip() or f"git status failed (exit {rc})")
        return Observation(ok=True, content=out.strip() or "clean (no changes)")


class GitDiffTool:
    name = "git_diff"
    args_model = GitArgs
    description = "Show the working-tree diff against HEAD (the candidate repair patch)."

    async def execute(self, args: GitArgs, ctx: ToolContext) -> Observation:
        rc, out, err = await _git(ctx.workspace, "diff")
        if rc != 0:
            return Observation(ok=False, error=err.strip() or f"git diff failed (exit {rc})")
        return Observation(ok=True, content=out)
