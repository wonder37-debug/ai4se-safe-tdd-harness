"""File tools: read_file / list_files / search_code.

Security upgrade over legacy ``fileTools.ts``: the workspace fence resolves
symlinks (``Path.resolve``) before the containment check, so a symlink pointing
outside the workspace cannot be used to read/write arbitrary host files.
All outputs are truncated to keep the LLM context bounded.
"""

from __future__ import annotations

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
    return full


def _walk(base: Path):
    for f in sorted(base.rglob("*")):
        if any(part in _SKIP_DIRS for part in f.relative_to(base).parts):
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


class SearchCodeTool:
    name = "search_code"
    args_model = SearchCodeArgs
    description = "Regex-search text files; returns file:line: text matches."

    async def execute(self, args: SearchCodeArgs, ctx: ToolContext) -> Observation:
        try:
            rx = re.compile(args.pattern)
        except re.error as e:
            return Observation(ok=False, error=f"invalid regex: {e}")
        try:
            base = _fence(ctx.workspace, args.path)
        except ValueError as e:
            return Observation(ok=False, error=str(e))
        hits: list[str] = []
        for f in _walk(base):
            if not f.is_file() or f.stat().st_size > _FILE_SIZE_CAP:
                continue
            try:
                lines = f.read_text(encoding="utf-8").splitlines()
            except (OSError, UnicodeDecodeError):
                continue
            rel = f.relative_to(base).as_posix()
            for i, line in enumerate(lines, 1):
                if rx.search(line):
                    hits.append(f"{rel}:{i}: {line.strip()}")
                    if len(hits) >= args.max_results:
                        return Observation(ok=True, content="\n".join(hits))
        return Observation(ok=True, content="\n".join(hits) if hits else "no matches")
