"""AgentLoop state machine: parity halt semantics + budgets, cancel, progress-aware retry."""

import asyncio

from safefix.agent.loop import AgentLoop, LoopDeps
from safefix.agent.state import Budgets, HaltReason
from safefix.feedback.classifier import FeedbackClassifier
from safefix.feedback.pytest_parser import PytestParser
from safefix.llm.base import LLMResponse
from safefix.llm.mock import ScriptedMock
from safefix.models import ApprovalDecision, TokenUsage, ToolCall
from safefix.runtime.executor import ExecResult
from safefix.security.approval import AutoApproveGateway, MockApprovalGateway
from safefix.tools.files import ListFilesTool, ReadFileTool
from safefix.tools.patch import ApplyPatchTool
from safefix.tools.registry import ToolRegistry
from safefix.tools.tests import RunTestsTool

FINISH = '```action\n{"tool": "finish", "args": {}}\n```'
LIST = '```action\n{"tool": "list_files", "args": {"path": "."}}\n```'

PYTEST_FAIL = """FAILED tests/test_math.py::test_add - assert 3 == 4
tests/test_math.py:4: AssertionError
1 failed
"""


class FakeExecutor:
    def __init__(self, result: ExecResult):
        self.result = result
        self.calls = 0

    async def run(self, command, *, cwd, timeout):
        self.calls += 1
        return self.result


class NativeMock:
    """Provider returning native tool calls (no fenced text)."""

    def __init__(self, responses: list[LLMResponse]):
        self._queue = list(responses)

    async def complete(self, messages):
        if not self._queue:
            raise RuntimeError("exhausted")
        return self._queue.pop(0)


def make_loop(tmp_path, responses, *, approval=None, executor=None, budgets=None, **kw):
    registry = ToolRegistry([ReadFileTool(), ListFilesTool(), ApplyPatchTool(), RunTestsTool()])
    deps = LoopDeps(
        llm=ScriptedMock(responses)
        if isinstance(responses, list) and all(isinstance(r, str) for r in responses)
        else responses,
        registry=registry,
        workspace=tmp_path,
        approval=approval or AutoApproveGateway(),
        feedback=FeedbackClassifier(PytestParser()),
        executor=executor,
        budgets=budgets or Budgets(),
        **kw,
    )
    return AgentLoop(deps)


async def test_finish_halts(tmp_path):
    result = await make_loop(tmp_path, [FINISH]).run()
    assert result.halt_reason == HaltReason.FINISH and result.iterations == 1


async def test_cap_with_sticky_mock(tmp_path):
    loop = make_loop(tmp_path, ScriptedMock([LIST], sticky=True), budgets=Budgets(max_llm_calls=3))
    result = await loop.run()
    assert result.halt_reason == HaltReason.CAP and result.iterations == 3


async def test_provider_error_halts(tmp_path):
    result = await make_loop(tmp_path, []).run()
    assert result.halt_reason == HaltReason.PROVIDER_ERROR


async def test_no_action_reprompts(tmp_path):
    loop = make_loop(tmp_path, ["just talking", FINISH])
    result = await loop.run()
    assert result.halt_reason == HaltReason.FINISH and result.iterations == 2
    assert any("no action block" in m.content for m in loop.messages)


async def test_multi_action_warning(tmp_path):
    two = LIST + "\n" + FINISH
    loop = make_loop(tmp_path, [two, FINISH])
    await loop.run()
    assert any(
        "仅执行首个 action" in m.content or "only the first action" in m.content for m in loop.messages
    )


async def test_high_risk_denied_feeds_back(tmp_path):
    dangerous = '```action\n{"tool": "run_tests", "args": {"command": "rm -rf /"}}\n```'
    ex = FakeExecutor(ExecResult(exit_code=0))
    loop = make_loop(
        tmp_path,
        [dangerous, FINISH],
        approval=MockApprovalGateway([ApprovalDecision(decision="deny", reason="too risky")]),
        executor=ex,
    )
    result = await loop.run()
    assert result.halt_reason == HaltReason.FINISH
    assert ex.calls == 0  # denied action never executed
    assert any("DENIED" in m.content for m in loop.messages)


async def test_deny_with_abort_intent_halts_immediately(tmp_path):
    dangerous = '```action\n{"tool": "run_tests", "args": {"command": "rm -rf /"}}\n```'
    loop = make_loop(
        tmp_path,
        [dangerous, FINISH],
        approval=MockApprovalGateway([ApprovalDecision(decision="deny", reason="stop, do not continue")]),
    )
    result = await loop.run()
    assert result.halt_reason == HaltReason.USER_ABORT and result.iterations == 1


async def test_low_risk_warns_but_executes(tmp_path):
    cmd = '```action\n{"tool": "run_tests", "args": {"command": "rm file.txt"}}\n```'
    ex = FakeExecutor(ExecResult(exit_code=0))
    loop = make_loop(tmp_path, [cmd, FINISH], executor=ex)
    await loop.run()
    assert ex.calls == 1
    assert any("WARN" in m.content for m in loop.messages)


async def test_stuck_after_repeated_same_failure(tmp_path):
    run = '```action\n{"tool": "run_tests", "args": {"command": "pytest -q"}}\n```'
    ex = FakeExecutor(ExecResult(stdout=PYTEST_FAIL, exit_code=1))
    loop = make_loop(
        tmp_path,
        ScriptedMock([run], sticky=True),
        executor=ex,
        budgets=Budgets(max_llm_calls=10, max_same_failure=3),
    )
    result = await loop.run()
    assert result.halt_reason == HaltReason.STUCK and ex.calls == 3


async def test_two_same_failures_not_stuck(tmp_path):
    run = '```action\n{"tool": "run_tests", "args": {"command": "pytest -q"}}\n```'
    ex = FakeExecutor(ExecResult(stdout=PYTEST_FAIL, exit_code=1))
    loop = make_loop(
        tmp_path,
        [run, run, FINISH],
        executor=ex,
        budgets=Budgets(max_same_failure=3),
    )
    result = await loop.run()
    assert result.halt_reason == HaltReason.FINISH  # parity upgrade: 2 repeats != impossible


async def test_successful_patch_resets_failure_counter(tmp_path):
    (tmp_path / "app.py").write_text("a = 1\n", encoding="utf-8")
    run = '```action\n{"tool": "run_tests", "args": {"command": "pytest -q"}}\n```'
    patch = (
        '```action\n{"tool": "apply_patch", "args": {"diff": '
        '"--- a/app.py\\n+++ b/app.py\\n@@ -1 +1 @@\\n-a = 1\\n+a = 2\\n"}}\n```'
    )
    ex = FakeExecutor(ExecResult(stdout=PYTEST_FAIL, exit_code=1))
    loop = make_loop(
        tmp_path,
        [run, run, patch, run, run, FINISH],
        executor=ex,
        budgets=Budgets(max_same_failure=3),
    )
    result = await loop.run()
    assert result.halt_reason == HaltReason.FINISH


async def test_cancel_before_start(tmp_path):
    ev = asyncio.Event()
    ev.set()
    loop = make_loop(tmp_path, [FINISH], cancel_event=ev)
    result = await loop.run()
    assert result.halt_reason == HaltReason.CANCELLED and result.iterations == 0


async def test_wall_clock_budget(tmp_path):
    clock = {"t": 0.0}

    def monotonic():
        clock["t"] += 100.0
        return clock["t"]

    loop = make_loop(
        tmp_path,
        ScriptedMock([LIST], sticky=True),
        budgets=Budgets(max_wall_seconds=1.0),
        monotonic=monotonic,
    )
    result = await loop.run()
    assert result.halt_reason == HaltReason.BUDGET_EXCEEDED


async def test_native_tool_call_finish(tmp_path):
    provider = NativeMock([LLMResponse(tool_calls=[ToolCall(name="finish")])])
    result = await make_loop(tmp_path, provider).run()
    assert result.halt_reason == HaltReason.FINISH


async def test_native_unknown_tool_feedback(tmp_path):
    provider = NativeMock(
        [
            LLMResponse(tool_calls=[ToolCall(name="drop_db")]),
            LLMResponse(tool_calls=[ToolCall(name="finish")]),
        ]
    )
    loop = make_loop(tmp_path, provider)
    result = await loop.run()
    assert result.halt_reason == HaltReason.FINISH
    assert any("unknown tool" in m.content for m in loop.messages)


async def test_events_recorded(tmp_path):
    from safefix.agent.events import EventLog

    log = EventLog()
    loop = make_loop(tmp_path, ["thinking\n" + FINISH], sink=log)
    await loop.run()
    types = [e.type for e in log.events]
    assert "thought" in types and "action" in types and "halt" in types


async def test_usage_accumulated(tmp_path):
    provider = NativeMock(
        [
            LLMResponse(text=LIST, usage=TokenUsage(prompt_tokens=10, completion_tokens=5)),
            LLMResponse(tool_calls=[ToolCall(name="finish")]),
        ]
    )
    result = await make_loop(tmp_path, provider).run()
    assert result.usage.prompt_tokens == 10 and result.usage.completion_tokens == 5
