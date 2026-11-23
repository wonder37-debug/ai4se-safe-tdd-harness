"""git_status / git_diff — hardened fixed-argv git calls on the disposable workspace.

No model-controlled shell string is involved: argv is constant, only the cwd is
the isolated task copy. Host git is a product dependency (repository management),
not an untrusted-execution path.

Hardening (review 4661696737): repository config can name EXECUTABLE commands
(core.fsmonitor hooks, diff.external/textconv drivers, hooksPath). Even though
apply_patch now refuses .git writes, a cloned target repo may already carry such
config. Every host git invocation therefore overrides the executable repo-config
keys (fsmonitor off, hooksPath neutralized) and diff calls use --no-ext-diff
--no-textconv. System/global config are host-admin controlled (not writable by
the target repo) and stay active so newline behavior remains consistent.
Output reads are bounded (host memory).
"""

from __future__ import annotations

import asyncio
import os

from pydantic import BaseModel

from safefix.models import Observation
from safefix.runtime.output import bounded_communicate
from safefix.tools.registry import ToolContext

_OUTPUT_CAP = 1_000_000

# Applied to EVERY host git call (prepended before the subcommand).
GIT_HARDEN_ARGS = [
    "-c",
    "core.fsmonitor=false",
    "-c",
    f"core.hooksPath={os.devnull}",
    "--no-optional-locks",
]
GIT_HARDEN_ENV = {
    **os.environ,
    "GIT_TERMINAL_PROMPT": "0",
}
# Extra flags for any diff-producing call (external drivers execute commands).
DIFF_SAFE_ARGS = ["--no-ext-diff", "--no-textconv"]


class GitArgs(BaseModel):
    pass


async def _git(workspace, *args: str) -> tuple[int, str, str]:
    proc = await asyncio.create_subprocess_exec(
        "git",
        *GIT_HARDEN_ARGS,
        *args,
        cwd=workspace,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=GIT_HARDEN_ENV,
    )
    out, err, timed_out = await bounded_communicate(proc, _OUTPUT_CAP, 30)
    if timed_out:
        proc.kill()
        await proc.wait()
        return -1, "", "git command timed out"
    return proc.returncode or 0, out, err


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
    description = "Show the full candidate change vs HEAD (tracked + new files)."

    async def execute(self, args: GitArgs, ctx: ToolContext) -> Observation:
        rc, out, err = await full_candidate_diff(ctx.workspace)
        if rc != 0:
            return Observation(ok=False, error=err.strip() or f"git diff failed (exit {rc})")
        return Observation(ok=True, content=out)


async def untracked_files(workspace) -> list[str]:
    """New files not in the index (info/exclude keeps tool junk out)."""
    rc, out, _ = await _git(workspace, "ls-files", "--others", "--exclude-standard")
    if rc != 0:
        return []
    return [line for line in out.splitlines() if line.strip()]


async def full_candidate_diff(workspace) -> tuple[int, str, str]:
    """Complete candidate change: tracked diff vs HEAD + synthesized new-file diffs.

    Deliberately avoids `git add` (which would execute repo-configured clean/smudge
    filter drivers on the host). Untracked files are diffed with --no-index.
    """
    rc, tracked, err = await _git(workspace, "diff", "HEAD", *DIFF_SAFE_ARGS)
    if rc != 0:
        return rc, tracked, err
    parts = [tracked] if tracked.strip() else []
    for rel in await untracked_files(workspace):
        rc2, out2, err2 = await _git(workspace, "diff", "--no-index", *DIFF_SAFE_ARGS, "--", "/dev/null", rel)
        if rc2 not in (0, 1):  # --no-index exits 1 when differences exist
            return rc2, "", err2
        if out2.strip():
            parts.append(out2)
    return 0, "\n".join(parts), ""
