"""File-backed memory store — port of legacy ``memoryStore.ts``.

Deliberately simple: task-local notes as ``<dir>/<key>.md`` files, injected into
the system prompt. No vector database / RAG (not justified by requirements).

Upgrade over the original: keys are validated against path traversal, and reads
are sorted by key for deterministic prompts.
"""

from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel

_KEY_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


class Note(BaseModel):
    key: str
    note: str


class MemoryStore:
    def __init__(self, directory: str | Path):
        self._dir = Path(directory)

    def _file(self, key: str) -> Path:
        if not _KEY_RE.match(key) or key in (".", ".."):
            raise ValueError(f"invalid memory key: {key!r}")
        return self._dir / f"{key}.md"

    async def read(self) -> list[Note]:
        try:
            files = sorted(self._dir.iterdir())
        except (FileNotFoundError, NotADirectoryError):
            return []
        return [
            Note(key=f.stem, note=f.read_text(encoding="utf-8"))
            for f in files
            if f.is_file() and f.suffix == ".md"
        ]

    async def write(self, key: str, note: str) -> None:
        path = self._file(key)
        self._dir.mkdir(parents=True, exist_ok=True)
        path.write_text(note, encoding="utf-8")

    async def clear(self, key: str) -> None:
        self._file(key).unlink(missing_ok=True)

    async def system_prompt(self) -> str:
        notes = await self.read()
        if not notes:
            return ""
        return "Project notes:\n" + "\n".join(f"- [{n.key}] {n.note}" for n in notes)
