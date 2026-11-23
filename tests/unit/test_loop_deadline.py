"""P2 regression: remaining wall-clock budget must bound IN-FLIGHT calls
(review 4663423547), including a late `finish` response.
"""

import asyncio

from safefix.agent.loop import AgentLoop, LoopDeps
from safefix.agent.state import Budgets, HaltReason
from safefix.feedback.classifier import FeedbackClassifier
from safefix.feedback.pytest_parser import PytestParser
from safefix.llm.base import LLMResponse
from safefix.models import Observation
from safefix.security.approval import AutoApproveGateway
from safefix.tools.registry import ToolRegistry


class SlowFinishProvider:
    def __init__(self, delay: float):
        self.delay = delay

    async def complete(self, messages):
        await asyncio.sleep(self.delay)
        return LLMResponse(text='```action\n{"tool": "finish", "args": {}}\n```')


class SlowTool:
    name = "run_tests"  # must be a protocol-registered tool name
    args_model = type("SlowArgs", (), {})
    description = "sleeps"

    async def execute(self, args, ctx):
        await asyncio.sleep(0.2)
        return Observation(ok=True)


def make_loop(tmp_path, provider, registry=None):
    return AgentLoop(
        LoopDeps(
            llm=provider,
            registry=registry or ToolRegistry([]),
            workspace=tmp_path,
            approval=AutoApproveGateway(),
            feedback=FeedbackClassifier(PytestParser()),
            budgets=Budgets(max_wall_seconds=0.02),
        )
    )


async def test_late_finish_cannot_beat_wall_budget(tmp_path):
    loop = make_loop(tmp_path, SlowFinishProvider(0.15))
    result = await loop.run()
    assert result.halt_reason == HaltReason.BUDGET_EXCEEDED
    assert result.duration_s < 0.1, "finish was accepted after the wall budget expired"


async def test_tool_execution_bounded_by_remaining_wall(tmp_path):
    from pydantic import BaseModel

    class SlowArgs(BaseModel):
        pass

    SlowTool.args_model = SlowArgs
    registry = ToolRegistry([SlowTool()])

    class SlowActionProvider:
        async def complete(self, messages):
            return LLMResponse(text='```action\n{"tool": "run_tests", "args": {"command": "pytest"}}\n```')

    loop = make_loop(tmp_path, SlowActionProvider(), registry)
    result = await loop.run()
    assert result.halt_reason == HaltReason.BUDGET_EXCEEDED
    assert result.duration_s < 0.15
