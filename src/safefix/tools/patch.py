"""apply_patch — minimal unified-diff editing, pure Python (no git binary needed).

Why not whole-file writes: minimal diffs keep repairs inspectable, reviewable and
safe; the verifier can reject unrelated destructive changes. The applier matches
hunk context exactly (searching the whole file when declared line numbers are
stale) and refuses on mismatch instead of corrupting the file.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import BaseModel, Field

from safefix.models import Observation
from safefix.tools.files import _fence
from safefix.tools.registry import ToolContext

_HUNK_RE = re.compile(r"@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@")


class PatchError(Exception):
    pass


@dataclass
class _Hunk:
    old_start: int
    old_lines: list[str] = field(default_factory=list)
    new_lines: list[str] = field(default_factory=list)


@dataclass
class _FilePatch:
    src: str | None
    dst: str | None
    hunks: list[_Hunk] = field(default_factory=list)


def _norm_path(raw: str) -> str | None:
    raw = raw.strip()
    if raw == "/dev/null":
        return None
    return re.sub(r"^[ab]/", "", raw)


def _parse(diff: str) -> list[_FilePatch]:
    lines = diff.splitlines()
    files: list[_FilePatch] = []
    i = 0
    while i < len(lines):
        if not lines[i].startswith("--- "):
            i += 1  # skip preamble (diff --git / index / mode lines)
            continue
        if i + 1 >= len(lines) or not lines[i + 1].startswith("+++ "):
            raise PatchError("missing +++ header after ---")
        fp = _FilePatch(src=_norm_path(lines[i][4:]), dst=_norm_path(lines[i + 1][4:]))
        i += 2
        while i < len(lines) and lines[i].startswith("@@"):
            m = _HUNK_RE.match(lines[i])
            if not m:
                raise PatchError(f"bad hunk header: {lines[i]!r}")
            hunk = _Hunk(old_start=int(m.group(1)))
            i += 1
            while i < len(lines):
                line = lines[i]
                if line.startswith("--- ") and i + 1 < len(lines) and lines[i + 1].startswith("+++ "):
                    break  # next file section
                if line.startswith("\\"):
                    i += 1  # "\ No newline at end of file"
                    continue
                if line[:1] not in (" ", "-", "+") and line != "":
                    break
                tag, content = (line[:1], line[1:]) if line else (" ", "")
                if tag in (" ", "-"):
                    hunk.old_lines.append(content)
                if tag in (" ", "+"):
                    hunk.new_lines.append(content)
                i += 1
            fp.hunks.append(hunk)
        if not fp.hunks:
            raise PatchError(f"no hunks for {fp.dst or fp.src}")
        files.append(fp)
    if not files:
        raise PatchError("no unified-diff file headers found")
    return files


def _find(lines: list[str], needle: list[str], hint: int) -> int | None:
    n = len(needle)
    if 0 <= hint <= len(lines) - n and lines[hint : hint + n] == needle:
        return hint
    for idx in range(len(lines) - n + 1):
        if lines[idx : idx + n] == needle:
            return idx
    return None


def _render(fp: _FilePatch, workspace: Path) -> tuple[Path, str | None]:
    """Compute the new content (or None for deletion) without writing yet."""
    if fp.dst is None:  # deletion
        if fp.src is None:
            raise PatchError("both sides are /dev/null")
        target = _fence(workspace, fp.src)
        if not target.exists():
            raise PatchError(f"cannot delete missing file: {fp.src}")
        return target, None
    target = _fence(workspace, fp.dst)
    if fp.src is None:  # creation
        if target.exists():
            raise PatchError(f"file already exists: {fp.dst}")
        new_lines: list[str] = []
        for h in fp.hunks:
            new_lines.extend(h.new_lines)
        return target, "\n".join(new_lines) + "\n"
    if not target.exists():
        raise PatchError(f"file not found: {fp.dst}")
    text = target.read_text(encoding="utf-8")
    trailing_nl = text.endswith("\n")
    lines = text.splitlines()
    for h in fp.hunks:
        if not h.old_lines:
            idx = max(0, min(h.old_start, len(lines)))
            lines[idx:idx] = h.new_lines
            continue
        idx = _find(lines, h.old_lines, h.old_start - 1)
        if idx is None:
            raise PatchError(f"hunk context mismatch in {fp.dst}")
        lines[idx : idx + len(h.old_lines)] = h.new_lines
    return target, "\n".join(lines) + ("\n" if trailing_nl else "")


class ApplyPatchArgs(BaseModel):
    diff: str = Field(description="Unified diff (--- a/path, +++ b/path, @@ hunks)")


class ApplyPatchTool:
    name = "apply_patch"
    args_model = ApplyPatchArgs
    description = "Apply a minimal unified diff to workspace files (create/modify/delete)."

    async def execute(self, args: ApplyPatchArgs, ctx: ToolContext) -> Observation:
        try:
            patches = _parse(args.diff)
            # two-phase: validate every file first, then write (no partial application)
            rendered = [_render(fp, ctx.workspace) for fp in patches]
            names = []
            for target, content in rendered:
                if content is None:
                    target.unlink()
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(content, encoding="utf-8")
                names.append(target.relative_to(ctx.workspace.resolve()).as_posix())
        except (PatchError, ValueError, OSError) as e:
            return Observation(ok=False, error=str(e))
        return Observation(ok=True, content=f"patched {len(names)} file(s): {', '.join(names)}")