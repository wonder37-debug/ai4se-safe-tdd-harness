"""LLM provider contract.

``LLMProvider`` is a structural Protocol so tests can inject deterministic mocks
and the loop never depends on a concrete HTTP client.
"""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, Field

from safefix.models import Message, TokenUsage, ToolCall


class LLMResponse(BaseModel):
    text: str = ""
    stop_reason: str = "ok"
    usage: TokenUsage = Field(default_factory=TokenUsage)
    tool_calls: list[ToolCall] = Field(default_factory=list)


class LLMProvider(Protocol):
    async def complete(self, messages: list[Message]) -> LLMResponse: ...
