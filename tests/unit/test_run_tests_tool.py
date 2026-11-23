"""run_tests tool delegates to the execution backend (never direct host exec)."""

from pathlib import Path

from safefix.models import Action
from safefix.runtime.executor import ExecResult
from safefix.tools.registry import ToolContext, ToolRegistry
from safefix.tools.tests import RunTestsTool


class FakeExecutor:
    def __init__(self, result: ExecResult):
        self.result = result
        self.calls: list[dict] = []

    async def run(self, command: str, *, cwd: Path, timeout: float) -> ExecResult:
        self.calls.append({"command": command, "cwd": cwd, "timeout": timeout})
        return self.result


def ctx(tmp_path, executor):
    return ToolContext(workspace=tmp_path, executor=executor)


async def test_run_tests_success(tmp_path):
    ex = FakeExecutor(ExecResult(stdout="1 passed", stderr="", exit_code=0))
    reg = ToolRegistry([RunTestsTool()])
    obs = await reg.dispatch(Action(tool="run_tests", args={"command": "pytest -q"}), ctx(tmp_path, ex))
    assert obs.ok and obs.exit_code == 0 and "1 passed" in obs.stdout
    assert ex.calls[0]["command"] == "pytest -q" and ex.calls[0]["cwd"] == tmp_path


async def test_run_tests_failure_maps_exit_code(tmp_path):
    ex = FakeExecutor(ExecResult(stdout="F", stderr="1 failed", exit_code=1))
    reg = ToolRegistry([RunTestsTool()])
    obs = await reg.dispatch(Action(tool="run_tests", args={"command": "pytest"}), ctx(tmp_path, ex))
    assert not obs.ok and obs.exit_code == 1


async def test_run_tests_timeout_maps_error(tmp_path):
    ex = FakeExecutor(ExecResult(stdout="", stderr="", exit_code=-1, timed_out=True))
    reg = ToolRegistry([RunTestsTool()])
    obs = await reg.dispatch(Action(tool="run_tests", args={"command": "pytest"}), ctx(tmp_path, ex))
    assert not obs.ok and obs.error == "timeout"


async def test_run_tests_empty_command_rejected(tmp_path):
    ex = FakeExecutor(ExecResult(exit_code=0))
    reg = ToolRegistry([RunTestsTool()])
    obs = await reg.dispatch(Action(tool="run_tests", args={"command": "  "}), ctx(tmp_path, ex))
    assert not obs.ok and ex.calls == []


async def test_run_tests_without_executor_explicit_error(tmp_path):
    reg = ToolRegistry([RunTestsTool()])
    obs = await reg.dispatch(Action(tool="run_tests", args={"command": "pytest"}), ctx(tmp_path, None))
    assert not obs.ok and "executor" in obs.error.lower()