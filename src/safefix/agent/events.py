"""Event sinks — port of legacy ``eventSink.ts`` (EventStore / fan-out).

Every loop decision is observable: thought / action / observation / approval /
halt events feed the CLI timeline, the JSONL audit trail and (optionally) the UI.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Protocol

from safefix.models import ExecutionEvent


class EventSink(Protocol):
    def emit(self, event: ExecutionEvent) -> None: ...


class NoopSink:
    def emit(self, event: ExecutionEvent) -> None:
        pass


class EventLog:
    """In-memory log; assigns monotonic sequence numbers and timestamps."""

    def __init__(self):
        self.events: list[ExecutionEvent] = []

    def emit(self, event: ExecutionEvent) -> None:
        self.events.append(event.model_copy(update={"seq": len(self.events) + 1, "ts": time.time()}))


class JsonlSink:
    """Append-only JSONL audit trail (one event per line)."""

    def __init__(self, path: str | Path):
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def emit(self, event: ExecutionEvent) -> None:
        with self._path.open("a", encoding="utf-8") as f:
            f.write(event.model_dump_json() + "\n")


class FanOutSink:
    def __init__(self, sinks: list[EventSink]):
        self._sinks = sinks

    def emit(self, event: ExecutionEvent) -> None:
        for s in self._sinks:
            s.emit(event)
