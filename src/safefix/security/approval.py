"""Human-in-the-loop approval gateways.

Port of legacy ``src/approval/approvalGateway.ts`` plus the abort-intent hard rule:
when a denial carries an explicit termination intent (Chinese or English), the
loop MUST halt immediately — the LLM may not look for alternative tools.
"""

from __future__ import annotations

import re
from typing import Protocol

from safefix.models import Action, ApprovalDecision


class ApprovalGateway(Protocol):
    async def request(self, action: Action, reasons: list[str]) -> ApprovalDecision: ...


def has_abort_intent(reason: str) -> bool:
    """Explicit termination intent in a denial reason (word-boundary English)."""
    s = reason.lower()
    if "终止" in s or "停止" in s or "不要执行了" in s:
        return True
    return re.search(r"\b(abort|cancel|stop)\b", s) is not None


class MockApprovalGateway:
    """Deterministic queue for tests; empty queue defaults to deny (fail-safe)."""

    def __init__(self, decisions: list[ApprovalDecision]):
        self._queue = list(decisions)

    async def request(self, action: Action, reasons: list[str]) -> ApprovalDecision:
        if not self._queue:
            return ApprovalDecision(decision="deny", reason="mock queue empty")
        return self._queue.pop(0)


class AutoApproveGateway:
    """For trusted demo/eval runs only — never the default for real tasks."""

    async def request(self, action: Action, reasons: list[str]) -> ApprovalDecision:
        return ApprovalDecision(decision="approve", reason="auto-approved (non-interactive mode)")


class AutoDenyGateway:
    """Fail-safe non-interactive gateway: high-risk actions are always denied."""

    async def request(self, action: Action, reasons: list[str]) -> ApprovalDecision:
        return ApprovalDecision(decision="deny", reason="auto-denied (non-interactive mode)")