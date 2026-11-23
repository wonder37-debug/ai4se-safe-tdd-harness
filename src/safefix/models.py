"""Core domain models for SafeFix (Pydantic v2).

Parity reference: legacy ``src/types.ts``. Field names follow Python snake_case;
the fenced action protocol still accepts the legacy JSON shape ``{"tool", "args"}``.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field

Role = Literal["system", "user", "assistant", "observation"]


class Message(BaseModel):
    role: Role
    content: str


class Action(BaseModel):
    """A single structured tool call emitted by the LLM (validated before dispatch)."""

    tool: str
    args: dict[str, Any] = Field(default_factory=dict)


class ToolCall(BaseModel):
    """Native OpenAI-style tool call (function calling), normalized for dispatch."""

    id: str = ""
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)

    def to_action(self) -> Action:
        return Action(tool=self.name, args=self.arguments)


class Observation(BaseModel):
    ok: bool
    stdout: str = ""
    stderr: str = ""
    exit_code: int | None = None
    error: str | None = None
    content: str | None = None


class FeedbackKind(StrEnum):
    PASS = "pass"
    ASSERTION = "assertion"
    SYNTAX = "syntax"
    TIMEOUT = "timeout"
    INFRASTRUCTURE = "infrastructure"
    UNEXPECTED = "unexpected"


class SourceLocation(BaseModel):
    file: str
    line: int
    snippet: str = ""


class Feedback(BaseModel):
    kind: FeedbackKind
    failed_tests: list[str] = Field(default_factory=list)
    location: SourceLocation | None = None
    evidence: str = ""
    hint: str = ""


Severity = Literal["none", "low", "high"]


class GuardrailVerdict(BaseModel):
    severity: Severity = "none"
    reasons: list[str] = Field(default_factory=list)


class SessionState(BaseModel):
    """Maintained by the loop; ``last_denied`` drives deny-escalation in the policy."""

    last_denied: bool = False


class ApprovalRequest(BaseModel):
    id: str
    action: Action
    reasons: list[str] = Field(default_factory=list)


class ApprovalDecision(BaseModel):
    decision: Literal["approve", "deny"]
    reason: str = ""


class TokenUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


EventType = Literal[
    "thought", "action", "observation", "approval_request", "approval_decision", "halt", "state"
]


class ExecutionEvent(BaseModel):
    seq: int
    type: EventType
    payload: dict[str, Any] = Field(default_factory=dict)
    iter: int = 0
    ts: float = 0.0
