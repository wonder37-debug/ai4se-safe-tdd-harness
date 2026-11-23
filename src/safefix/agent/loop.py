"""AgentLoop — explicit state machine, port of legacy ``agentLoop.ts`` + upgrades.

Preserved halt semantics: finish / cap / stuck / provider_error / user_abort.
Upgrades:
- explicit ``TaskState`` + resource budgets (LLM calls, steps, wall clock, tokens);
- cooperative cancellation via ``asyncio.Event``;
- progress-aware bounded retry: a successful patch resets the repeated-failure
  counter, and the default threshold is 3 (the legacy "2 repeats => stuck" was
  too aggressive — the same error twice is not proof of impossibility);
- native tool calls and fenced-action fallback share one dispatch path;
- every decision emits an event (audit trail).

All mechanisms are deterministic functions testable with a scripted mock LLM and
no network — the grading property of the original harness is preserved.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from safefix.agent.events import EventSink, NoopSink
from safefix.agent.protocol import parse_actions, strip_action_fences
from safefix.agent.state import Budgets, HaltReason, LoopResult, TaskState
from safefix.feedback.classifier import FeedbackClassifier
from safefix.llm.base import LLMProvider
from safefix.memory.store import MemoryStore
from safefix.models import (
    Action,
    ExecutionEvent,
    GuardrailVerdict,
    Message,
    SessionState,
    TokenUsage,
)
from safefix.runtime.executor import ExecutionBackend
from safefix.security.approval import ApprovalGateway, has_abort_intent
from safefix.security.policy import assess as default_policy
from safefix.tools.registry import ToolContext, ToolRegistry

PolicyFn = Callable[[Action, SessionState | None], GuardrailVerdict]


@dataclass
class LoopDeps:
    llm: LLMProvider
    registry: ToolRegistry
    workspace: Path
    approval: ApprovalGateway
    feedback: FeedbackClassifier
    budgets: Budgets = field(default_factory=Budgets)
    system_prompt: str = "You are SafeFix, a safe coding agent. Complete the task using tools."
    policy: PolicyFn | None = None
    memory: MemoryStore | None = None
    sink: EventSink | None = None
    executor: ExecutionBackend | None = None
    cancel_event: asyncio.Event | None = None
    monotonic: Callable[[], float] = time.monotonic


class AgentLoop:
    def __init__(self, deps: LoopDeps):
        self.deps = deps
        self.state = TaskState.RUNNING
        self.messages: list[Message] = [
            Message(role="system", content=deps.system_prompt),
            Message(role="user", content="complete the task using tools"),
        ]
        self._session = SessionState()
        self._sink = deps.sink or NoopSink()
        self._policy = deps.policy or default_policy
        self._iter = 0

    def _emit(self, type_: str, payload: dict) -> None:
        self._sink.emit(ExecutionEvent(seq=0, type=type_, payload=payload, iter=self._iter))

    def _halt(self, reason: HaltReason, result: LoopResult, **payload) -> LoopResult:
        self.state = TaskState.HALTED
        self._emit("halt", {"reason": reason.value, **payload})
        return result.model_copy(update={"halt_reason": reason})

    async def run(self) -> LoopResult:
        deps = self.deps
        start = deps.monotonic()
        result = LoopResult(halt_reason=HaltReason.CAP)

        if deps.memory is not None:
            mem = await deps.memory.system_prompt()
            if mem:
                self.messages[0].content += "\n\n" + mem

        usage = TokenUsage()
        llm_calls = 0
        steps = 0
        last_fail_key: str | None = None
        same_count = 0
        ctx = ToolContext(workspace=deps.workspace, executor=deps.executor)

        def snapshot(reason: HaltReason) -> LoopResult:
            return LoopResult(
                halt_reason=reason,
                iterations=self._iter,
                llm_calls=llm_calls,
                steps=steps,
                usage=usage,
                duration_s=deps.monotonic() - start,
            )

        while True:
            if deps.cancel_event is not None and deps.cancel_event.is_set():
                return self._halt(HaltReason.CANCELLED, snapshot(HaltReason.CANCELLED))
            if self._iter >= deps.budgets.max_llm_calls:
                return self._halt(HaltReason.CAP, snapshot(HaltReason.CAP))
            if deps.monotonic() - start > deps.budgets.max_wall_seconds:
                return self._halt(HaltReason.BUDGET_EXCEEDED, snapshot(HaltReason.BUDGET_EXCEEDED), budget="wall_seconds")
            if deps.budgets.max_tokens and usage.total_tokens >= deps.budgets.max_tokens:
                return self._halt(HaltReason.BUDGET_EXCEEDED, snapshot(HaltReason.BUDGET_EXCEEDED), budget="tokens")

            self._iter += 1
            llm_calls += 1
            try:
                resp = await deps.llm.complete(self.messages)
            except Exception as e:
                return self._halt(
                    HaltReason.PROVIDER_ERROR, snapshot(HaltReason.PROVIDER_ERROR), error=f"provider_error: {e}"
                )
            usage = TokenUsage(
                prompt_tokens=usage.prompt_tokens + resp.usage.prompt_tokens,
                completion_tokens=usage.completion_tokens + resp.usage.completion_tokens,
            )
            self.messages.append(Message(role="assistant", content=resp.text))
            said = strip_action_fences(resp.text)
            if said:
                self._emit("thought", {"text": said})

            if resp.tool_calls:
                acts = [tc.to_action() for tc in resp.tool_calls]
            else:
                acts = parse_actions(resp.text)
            if not acts:
                self.messages.append(
                    Message(role="user", content="Observation: no action block found; emit a fenced ```action {...}``` block")
                )
                continue
            if len(acts) > 1:
                self.messages.append(
                    Message(
                        role="user",
                        content=f"Observation: 仅执行首个 action，忽略其余 {len(acts) - 1} 个（每轮只允许一个 action 块）",
                    )
                )
            action = acts[0]
            self._emit("action", action.model_dump())

            if action.tool == "finish":
                # the agent only CLAIMS completion; the independent verifier decides success
                return self._halt(HaltReason.FINISH, snapshot(HaltReason.FINISH))

            verdict = self._policy(action, self._session)
            if verdict.severity == "high":
                self.state = TaskState.WAITING_APPROVAL
                self._emit("approval_request", {"action": action.model_dump(), "reasons": verdict.reasons})
                dec = await deps.approval.request(action, verdict.reasons)
                self._emit("approval_decision", dec.model_dump())
                self.state = TaskState.RUNNING
                if dec.decision == "deny":
                    if has_abort_intent(dec.reason):
                        return self._halt(
                            HaltReason.USER_ABORT, snapshot(HaltReason.USER_ABORT), user_reason=dec.reason
                        )
                    self._session.last_denied = True
                    self.messages.append(
                        Message(role="user", content=f"Observation: DENIED: {dec.reason} (reasons: {'; '.join(verdict.reasons)})")
                    )
                    continue
            elif verdict.severity == "low":
                self.messages.append(
                    Message(role="user", content=f"Observation: WARN(low): {'; '.join(verdict.reasons)}")
                )

            self._session.last_denied = False
            if steps >= deps.budgets.max_steps:
                return self._halt(HaltReason.BUDGET_EXCEEDED, snapshot(HaltReason.BUDGET_EXCEEDED), budget="steps")
            obs = await deps.registry.dispatch(action, ctx)
            steps += 1

            if action.tool == "run_tests" and not obs.ok:
                fb = deps.feedback.parse(obs)
                loc = f"{fb.location.file}:{fb.location.line}" if fb.location else ""
                key = f"{fb.kind.value}|{','.join(sorted(fb.failed_tests))}|{loc}"
                if key == last_fail_key:
                    same_count += 1
                else:
                    same_count = 1
                    last_fail_key = key
                self.messages.append(Message(role="user", content=f"Observation: {fb.model_dump_json()}"))
                self._emit("observation", fb.model_dump())
                if same_count >= deps.budgets.max_same_failure:
                    return self._halt(HaltReason.STUCK, snapshot(HaltReason.STUCK), key=key)
            else:
                self.messages.append(Message(role="user", content=f"Observation: {obs.model_dump_json()}"))
                self._emit("observation", obs.model_dump())
                if action.tool == "apply_patch" and obs.ok:
                    # actual progress: a landed patch resets the repeated-failure counter
                    same_count = 0
                    last_fail_key = None