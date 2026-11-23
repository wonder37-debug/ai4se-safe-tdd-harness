"""Disposable workspace management.

The target repository is NEVER modified: we clone it (local ``--no-hardlinks``
clone or remote URL clone) into a fresh temporary directory and record the base
commit SHA. All agent edits happen in the copy; cleanup removes it.

NOTE: a clone/copy protects source history — it is NOT a security sandbox.
Untrusted command execution still goes through the Docker executor.
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from safefix.tools.git import GIT_HARDEN_ARGS, GIT_HARDEN_ENV

# Tool-generated artifacts that must never enter the candidate patch.
_EXCLUDES = [
    ".safefix-memory/",
    ".deps/",
    "__pycache__/",
    "*.pyc",
    "_eval_verify/",
    ".pytest_cache/",
    ".ruff_cache/",
]


class WorkspaceError(Exception):
    pass


@dataclass
class Workspace:
    path: Path
    base_commit: str
    source: str


def _git(cwd: Path | None, *args: str) -> str:
    proc = subprocess.run(
        ["git", *GIT_HARDEN_ARGS, *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=300,
        env=GIT_HARDEN_ENV,
    )
    if proc.returncode != 0:
        raise WorkspaceError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout.strip()


def _ensure_container_writable(dest: Path) -> None:
    """Root host (native Linux): the clone is root-owned 0755/0644, so a non-root
    container user cannot write it. Transfer ownership to the sandbox uid while
    KEEPING the container non-root (review 4663355656). No-op elsewhere.

    Never follow symlinks (review 4664964008): a repo symlink pointing at a host
    file must not have its TARGET chowned — ownership changes stay strictly on
    objects inside the clone.
    """
    if not hasattr(os, "geteuid") or os.geteuid() != 0:
        return
    for path in [dest, *dest.rglob("*")]:
        try:
            if path.is_symlink():
                continue
            os.chown(path, 1000, 1000, follow_symlinks=False)
        except OSError:
            pass


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
    # keep tool artifacts out of `git ls-files --others --exclude-standard`
    info_dir = dest / ".git" / "info"
    info_dir.mkdir(parents=True, exist_ok=True)
    exclude = info_dir / "exclude"
    existing = exclude.read_text(encoding="utf-8") if exclude.exists() else ""
    exclude.write_text(existing + "\n" + "\n".join(_EXCLUDES) + "\n", encoding="utf-8")
    _ensure_container_writable(dest)
    return Workspace(path=dest, base_commit=base_commit, source=source)


def _on_rm_error(func, path, exc_info):
    # Windows: git object files are read-only; chmod then retry once.
    Path(path).chmod(stat.S_IWRITE)
    func(path)


def cleanup_workspace(ws: Workspace) -> None:
    if ws.path.exists():
        shutil.rmtree(ws.path, onexc=_on_rm_error)
