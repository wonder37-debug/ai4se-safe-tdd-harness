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
from pathlib import Path, PurePosixPath

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


async def _git(workspace, *args: str, git_dir: Path | None = None) -> tuple[int, str, str]:
    prefix = []
    if git_dir is not None:
        # frozen sanitized metadata: container cannot influence config/HEAD/index
        prefix = ["--git-dir", str(git_dir), "--work-tree", str(workspace)]
    proc = await asyncio.create_subprocess_exec(
        "git",
        *prefix,
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
        rc, out, err = await _git(ctx.workspace, "status", "--porcelain", git_dir=ctx.git_dir)
        if rc != 0:
            return Observation(ok=False, error=err.strip() or f"git status failed (exit {rc})")
        return Observation(ok=True, content=out.strip() or "clean (no changes)")


class GitDiffTool:
    name = "git_diff"
    args_model = GitArgs
    description = "Show the full candidate change vs HEAD (tracked + new files)."

    async def execute(self, args: GitArgs, ctx: ToolContext) -> Observation:
        rc, out, err = await full_candidate_diff(ctx.workspace, ctx.git_dir)
        if rc != 0:
            return Observation(ok=False, error=err.strip() or f"git diff failed (exit {rc})")
        return Observation(ok=True, content=out)


# Harness-controlled exclusions for untracked enumeration. Deliberately NOT the
# workspace .gitignore / info/exclude: the agent can edit those to hide protected
# files (review 4665404091). Tool artifacts are excluded by fixed rules instead.
_UNTRACKED_SKIP_DIRS = {
    ".git",
    ".deps",
    "__pycache__",
    ".safefix-memory",
    "_eval_verify",
    ".pytest_cache",
    ".ruff_cache",
}


async def untracked_files(workspace, git_dir: Path | None = None) -> list[str]:
    """All untracked files, filtered by HARNESS rules (not workspace ignore rules)."""
    rc, out, _ = await _git(workspace, "ls-files", "--others", git_dir=git_dir)
    if rc != 0:
        return []
    result = []
    for line in out.splitlines():
        rel = line.strip()
        if not rel:
            continue
        parts = PurePosixPath(rel).parts
        if any(p in _UNTRACKED_SKIP_DIRS for p in parts) or rel.endswith(".pyc"):
            continue
        result.append(rel)
    return result


_TRUNC_MARKER = "...[output truncated]"


async def full_candidate_diff(workspace, git_dir: Path | None = None) -> tuple[int, str, str]:
    """Complete candidate change vs the FROZEN base: tracked diff + new-file diffs.

    Deliberately avoids `git add` (which would execute repo-configured clean/smudge
    filter drivers on the host). Untracked files are diffed with --no-index.
    A truncated diff is NEVER delivered as a patch (review 4665182729): explicit
    failure instead of a silently incomplete candidate.
    """
    rc, tracked, err = await _git(workspace, "diff", "HEAD", *DIFF_SAFE_ARGS, git_dir=git_dir)
    if rc != 0:
        return rc, tracked, err
    if _TRUNC_MARKER in tracked:
        return -1, "", "candidate diff exceeded output cap; refusing to deliver a truncated patch"
    parts = [tracked] if tracked.strip() else []
    for rel in await untracked_files(workspace, git_dir):
        rc2, out2, err2 = await _git(
            workspace, "diff", "--no-index", *DIFF_SAFE_ARGS, "--", "/dev/null", rel, git_dir=git_dir
        )
        if rc2 not in (0, 1):  # --no-index exits 1 when differences exist
            return rc2, "", err2
        if _TRUNC_MARKER in out2:
            return -1, "", f"new-file diff for {rel} exceeded output cap; refusing truncated patch"
        if out2.strip():
            parts.append(out2)
    return 0, "\n".join(parts), ""
