"""Full repair workflow INSIDE the Docker sandbox (live integration).

Trusted prep installs pytest into the workspace (.deps) with controlled network;
all agent/verification test runs then execute with --network none. Skipped when
the daemon is unreachable — labelled NOT RUN, never faked.
"""

import json
import subprocess

import pytest

from safefix.agent.state import Budgets
from safefix.evaluation.fixtures import load_fixture, materialize_fixture
from safefix.llm.mock import ScriptedMock
from safefix.repair.workflow import RepairTask, run_repair
from safefix.runtime.docker_executor import DockerExecutor
from safefix.security.approval import AutoApproveGateway


def _docker_available() -> bool:
    try:
        subprocess.run(["docker", "info"], capture_output=True, timeout=20, check=True)
        return True
    except (OSError, subprocess.SubprocessError):
        return False


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not _docker_available(), reason="Docker daemon unavailable — sandboxed repair NOT RUN"
    ),
]

FIX_DIFF = (
    "--- a/shop/paginate.py\n"
    "+++ b/shop/paginate.py\n"
    "@@ -5,3 +5,3 @@\n"
    '     """Return the ``page``-th (1-based) slice of ``items`` with ``size`` per page."""\n'
    "-    start = page * size\n"
    "+    start = (page - 1) * size\n"
    "     return items[start : start + size]\n"
)


def action(tool, args):
    return "```action\n" + json.dumps({"tool": tool, "args": args}) + "\n```"


async def test_sandboxed_repair_verified(tmp_path):
    source = materialize_fixture("paginate", tmp_path / "source")
    fx = load_fixture("paginate")
    executor = DockerExecutor()
    py = "PYTHONPATH=.deps python -m pytest -q"

    outcome = await run_repair(
        RepairTask(
            repo=str(source),
            issue=fx.meta["issue"],
            test_command=py,
            repro_command=f"{py} tests/test_paginate.py",
            eval_dir=fx.eval_dir,
            eval_command=f"{py} _eval_verify",
            setup_commands=["pip install --quiet --target .deps pytest"],
            budgets=Budgets(max_llm_calls=12, max_wall_seconds=900),
        ),
        provider=ScriptedMock(
            [
                action("run_tests", {"command": f"{py} tests/test_paginate.py", "timeout": 300}),
                action("read_file", {"path": "shop/paginate.py"}),
                action("apply_patch", {"diff": FIX_DIFF}),
                action("run_tests", {"command": py, "timeout": 300}),
                action("finish", {}),
            ]
        ),
        executor=executor,
        approval=AutoApproveGateway(),
        report_dir=tmp_path / "report",
    )

    assert outcome.status == "verified", outcome.failure_analysis
    assert "(page - 1) * size" in outcome.patch
    assert outcome.verification.verified
    # original repo untouched
    status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=source, capture_output=True, text=True, check=True
    ).stdout
    assert status.strip() == ""
