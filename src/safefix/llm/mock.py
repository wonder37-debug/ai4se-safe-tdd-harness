"""Deterministic scripted mock provider — port of legacy ``scriptedMock.ts``.

Used for offline unit tests and the explicit ``demo`` mode. NEVER substituted
silently for a real provider: mode selection is explicit in the CLI/config.
"""

from __future__ import annotations

from safefix.llm.base import LLMResponse
from safefix.models import Message


class ScriptedMock:
    def __init__(self, responses: list[str], sticky: bool = False):
        self._queue = list(responses)
        self._sticky = sticky
        self._last: str | None = None

    async def complete(self, messages: list[Message]) -> LLMResponse:
        if self._queue:
            self._last = self._queue.pop(0)
            return LLMResponse(text=self._last)
        if self._sticky and self._last is not None:
            return LLMResponse(text=self._last)
        raise RuntimeError("ScriptedMock: response queue exhausted and not sticky")
