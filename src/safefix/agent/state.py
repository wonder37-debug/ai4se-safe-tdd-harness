"""Explicit task states, halt reasons and resource budgets."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from safefix.models import TokenUsage


class TaskState(str, Enum):
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    HALTED = "halted"


class HaltReason(str, Enum):
    FINISH = "finish"
    CAP = "cap"
    STUCK = "stuck"
    PROVIDER_ERROR = "provider_error"
    USER_ABORT = "user_abort"
    BUDGET_EXCEEDED = "budget_exceeded"
    CANCELLED = "cancelled"


class Budgets(BaseModel):
    max_llm_calls: int = Field(default=20, ge=1)
    max_steps: int = Field(default=40, ge=1)
    max_wall_seconds: float = Field(default=600.0, gt=0)
    max_tokens: int = Field(default=0, ge=0)  # 0 = unlimited
    max_same_failure: int = Field(default=3, ge=1)


class LoopResult(BaseModel):
    halt_reason: HaltReason
    iterations: int = 0
    llm_calls: int = 0
    steps: int = 0
    usage: TokenUsage = Field(default_factory=TokenUsage)
    duration_s: float = 0.0