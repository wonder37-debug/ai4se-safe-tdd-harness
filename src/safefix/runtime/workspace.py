"""Disposable workspace management.

The target repository is NEVER modified: we clone it (local ``--no-hardlinks``
clone or remote URL clone) into a fresh temporary directory and record the base
commit SHA. All agent edits happen in the copy; cleanup removes it.

NOTE: a clone/copy protects source history — it is NOT a security sandbox.
Untrusted command execution still goes through the Docker executor.
"""

from __future__ import annotations

import shutil
import stat
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path


class WorkspaceError(Exception):
    pass


@dataclass
class Workspace:
    path: Path
    base_commit: str
    source: str


def _git(cwd: Path | None, *args: str) -> str:
    proc = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, timeout=300
    )
    if proc.returncode != 0:
        raise WorkspaceError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout.strip()


def prepare_workspace(repo: str, *, dest: Path | None = None) -> Workspace:
    """Clone ``repo`` (local path or Git URL) into an isolated disposable copy."""
    src = Path(repo)
    if dest is None:
        dest = Path(tempfile.mkdtemp(prefix="safefix-")) / "repo"
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)

    if src.exists():
        if not (src / ".git").exists():
            raise WorkspaceError(f"not a git repository: {repo}")
        _git(None, "clone", "--local", "--no-hardlinks", "--quiet", str(src), str(dest))
        source = str(src)
    else:
        # treat as URL (trusted preparation step; network allowed here by design)
        _git(None, "clone", "--depth", "1", "--quiet", repo, str(dest))
        source = repo

    base_commit = _git(dest, "rev-parse", "HEAD")
    return Workspace(path=dest, base_commit=base_commit, source=source)


def _on_rm_error(func, path, exc_info):
    # Windows: git object files are read-only; chmod then retry once.
    Path(path).chmod(stat.S_IWRITE)
    func(path)


def cleanup_workspace(ws: Workspace) -> None:
    if ws.path.exists():
        shutil.rmtree(ws.path, onexc=_on_rm_error)