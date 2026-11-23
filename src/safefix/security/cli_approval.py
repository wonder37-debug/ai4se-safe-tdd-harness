"""Interactive CLI approval gateway (HITL).

[y] approve / [n] deny / free text = deny-with-feedback. A denial carrying an
explicit abort intent halts the loop (handled by AgentLoop, not here).
"""

from __future__ import annotations

from collections.abc import Callable

from safefix.models import Action, ApprovalDecision


class CliApprovalGateway:
    def __init__(self, ask: Callable[[str], str] | None = None, show: Callable[[str], None] | None = None):
        self._ask = ask or (lambda prompt: input(prompt))
        self._show = show or (lambda text: print(text))

    async def request(self, action: Action, reasons: list[str]) -> ApprovalDecision:
        self._show(f"\n[approval] high-risk action: {action.tool} {action.args}")
        for r in reasons:
            self._show(f"  - {r}")
        answer = self._ask("approve? [y] yes / [n] no / or type feedback to deny: ").strip()
        if answer.lower() in ("y", "yes"):
            return ApprovalDecision(decision="approve", reason="user approved")
        if answer.lower() in ("n", "no", ""):
            return ApprovalDecision(decision="deny", reason="user denied")
        return ApprovalDecision(decision="deny", reason=answer)
