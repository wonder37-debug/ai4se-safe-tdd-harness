"""File tools: read_file / list_files / search_code.

Security upgrade over legacy ``fileTools.ts``: the workspace fence resolves
symlinks (``Path.resolve``) before the containment check, so a symlink pointing
outside the workspace cannot be used to read/write arbitrary host files.
All outputs are truncated to keep the LLM context bounded.
"""

from __future__ import annotations

import asyncio
import multiprocessing as mp
import re
from pathlib import Path

from pydantic import BaseModel, Field

from safefix.models import Observation
from safefix.tools.registry import ToolContext

_READ_CAP = 20_000
_LIST_CAP = 500
_FILE_SIZE_CAP = 1_000_000
_SKIP_DIRS = {".git", "__pycache__", ".venv", "node_modules", ".pytest_cache", ".ruff_cache"}


def _fence(workspace: Path, p: str) -> Path:
    root = workspace.resolve()
    full = Path(root, p).resolve()
    if not full.is_relative_to(root):
        raise ValueError(f"path escapes workspace: {p!r}")
    if ".git" in full.relative_to(root).parts:
        # Git metadata can carry executable config (core.fsmonitor, hooks,
        # diff drivers); host git calls must never see model-written values.
        raise ValueError(f"path touches .git metadata: {p!r}")
    return full


def _walk(base: Path):
    root = base.resolve()
    for f in sorted(base.rglob("*")):
        if any(part in _SKIP_DIRS for part in f.relative_to(base).parts):
            continue
        try:
            # per-entry symlink fence: file symlinks pointing outside the
            # workspace must not be stat'd/read (host data leak via search).
            if not f.resolve().is_relative_to(root):
                continue
        except OSError:
            continue
        yield f


class ReadFileArgs(BaseModel):
    path: str = Field(description="File path relative to the workspace root")


class ReadFileTool:
    name = "read_file"
    args_model = ReadFileArgs
    description = "Read a UTF-8 text file inside the workspace (truncated if large)."

    async def execute(self, args: ReadFileArgs, ctx: ToolContext) -> Observation:
        try:
            full = _fence(ctx.workspace, args.path)
            text = full.read_text(encoding="utf-8")
        except FileNotFoundError:
            return Observation(ok=False, error=f"file not found: {args.path}")
        except (OSError, ValueError, UnicodeDecodeError) as e:
            return Observation(ok=False, error=str(e))
        if len(text) > _READ_CAP:
            text = text[:_READ_CAP] + "\n...[truncated]"
        return Observation(ok=True, content=text)


class ListFilesArgs(BaseModel):
    path: str = Field(default=".", description="Directory relative to the workspace root")
    recursive: bool = Field(default=True, description="List nested files too")


class ListFilesTool:
    name = "list_files"
    args_model = ListFilesArgs
    description = "List files in a workspace directory (skips .git and caches)."

    async def execute(self, args: ListFilesArgs, ctx: ToolContext) -> Observation:
        try:
            base = _fence(ctx.workspace, args.path)
            if not base.is_dir():
                return Observation(ok=False, error=f"not a directory: {args.path}")
            entries = (
                _walk(base)
                if args.recursive
                else (f for f in sorted(base.iterdir()) if f.name not in _SKIP_DIRS)
            )
            names = [f.relative_to(base).as_posix() + ("/" if f.is_dir() else "") for f in entries]
        except (OSError, ValueError) as e:
            return Observation(ok=False, error=str(e))
        if len(names) > _LIST_CAP:
            names = names[:_LIST_CAP] + ["...[truncated]"]
        return Observation(ok=True, content="\n".join(names))


class SearchCodeArgs(BaseModel):
    pattern: str = Field(description="Python regular expression to search for")
    path: str = Field(default=".", description="Directory to search, relative to workspace")
    max_results: int = Field(default=50, ge=1, le=500)
    timeout: float = Field(default=10.0, gt=0, le=60, description="Hard search deadline in seconds")


def _search_worker(base_str: str, pattern: str, max_results: int, conn) -> None:
    """Runs in a KILLABLE child process: catastrophic regex backtracking cannot
    hang the host event loop; the parent terminates it on deadline."""
    try:
        base = Path(base_str)
        root = base.resolve()
        rx = re.compile(pattern)
        hits: list[str] = []
        for f in _walk(base):
            try:
                resolved = f.resolve()
                if not resolved.is_relative_to(root):
                    continue
                if not resolved.is_file() or resolved.stat().st_size > _FILE_SIZE_CAP:
                    continue
                lines = resolved.read_text(encoding="utf-8").splitlines()
            except (OSError, UnicodeDecodeError):
                continue
            rel = f.relative_to(base).as_posix()
            for i, line in enumerate(lines, 1):
                if rx.search(line):
                    hits.append(f"{rel}:{i}: {line.strip()}")
                    if len(hits) >= max_results:
                        conn.send(("ok", "\n".join(hits)))
                        return
        conn.send(("ok", "\n".join(hits) if hits else "no matches"))
    except Exception as e:  # noqa: BLE001 - report any worker failure to parent
        try:
            conn.send(("err", str(e)))
        except Exception:
            pass
    finally:
        conn.close()


def _run_search_process(base_str: str, pattern: str, max_results: int, timeout: float) -> Observation:
    ctx = mp.get_context("spawn")  # fork is unsafe inside a worker thread
    parent_conn, child_conn = ctx.Pipe(duplex=False)
    proc = ctx.Process(target=_search_worker, args=(base_str, pattern, max_results, child_conn))
    proc.start()
    child_conn.close()
    try:
        if parent_conn.poll(timeout):
            status, payload = parent_conn.recv()
            if status == "ok":
                return Observation(ok=True, content=payload)
            return Observation(ok=False, error=payload)
        return Observation(ok=False, error=f"search timed out after {timeout}s (process terminated)")
    except (EOFError, OSError) as e:
        return Observation(ok=False, error=f"search worker failed: {e}")
    finally:
        parent_conn.close()
        proc.join(1)
        if proc.is_alive():
            proc.terminate()
            proc.join(2)
            if proc.is_alive():
                proc.kill()
                proc.join()


class SearchCodeTool:
    name = "search_code"
    args_model = SearchCodeArgs
    description = "Regex-search text files; returns file:line: text matches."

    async def execute(self, args: SearchCodeArgs, ctx: ToolContext) -> Observation:
        try:
            re.compile(args.pattern)
        except re.error as e:
            return Observation(ok=False, error=f"invalid regex: {e}")
        try:
            base = _fence(ctx.workspace, args.path)
        except ValueError as e:
            return Observation(ok=False, error=str(e))
        # off the event loop: the child process is killable on deadline
        return await asyncio.to_thread(
            _run_search_process, str(base), args.pattern, args.max_results, args.timeout
        )
