"""End-to-end repair workflow (offline, deterministic mock LLM + trusted local executor).

Demonstrates the REAL product workflow on a genuine bug fixture:
tests fail at base -> source patch -> tests pass -> independent verification ->
git diff produced -> original repository untouched. The LLM is scripted (no
network); a live-model run is a separate, explicitly labelled integration test.
"""

import json
import subprocess

from local_executor import TrustedLocalExecutor

from safefix.agent.state import Budgets
from safefix.evaluation.fixtures import load_fixture, materialize_fixture
from safefix.llm.mock import ScriptedMock
from safefix.repair.workflow import RepairTask, run_repair
from safefix.security.approval import AutoApproveGateway

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


def make_responses():
    return [
        action("run_tests", {"command": "python -m pytest -q tests/test_paginate.py"}),
        action("read_file", {"path": "shop/paginate.py"}),
        action("apply_patch", {"diff": FIX_DIFF}),
        action("run_tests", {"command": "python -m pytest -q"}),
        action("finish", {}),
    ]


async def test_full_repair_verified(tmp_path):
    source = materialize_fixture("paginate", tmp_path / "source")
    fx = load_fixture("paginate")
    report_dir = tmp_path / "report"
    executor = TrustedLocalExecutor()

    outcome = await run_repair(
        RepairTask(
            repo=str(source),
            issue=fx.meta["issue"],
            test_command=fx.meta["test_command"],
            repro_command=fx.meta["repro_command"],
            eval_dir=fx.eval_dir,
            budgets=Budgets(max_llm_calls=12),
        ),
        provider=ScriptedMock(make_responses()),
        executor=executor,
        approval=AutoApproveGateway(),
        report_dir=report_dir,
    )

    assert outcome.status == "verified", outcome.failure_analysis
    assert outcome.repro_before is not None and not outcome.repro_before.passed
    assert "(page - 1) * size" in outcome.patch
    assert outcome.base_commit
    assert outcome.verification.verified
    assert (report_dir / "patch.diff").exists()
    assert (report_dir / "events.jsonl").exists()
    assert (report_dir / "outcome.json").exists()

    # original repository untouched
    assert (source / "shop" / "paginate.py").read_text(encoding="utf-8").count("page * size") == 1
    status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=source, capture_output=True, text=True, check=True
    ).stdout
    assert status.strip() == ""


async def test_finish_without_patch_is_not_success(tmp_path):
    source = materialize_fixture("paginate", tmp_path / "source")
    fx = load_fixture("paginate")
    outcome = await run_repair(
        RepairTask(repo=str(source), issue=fx.meta["issue"], eval_dir=fx.eval_dir),
        provider=ScriptedMock([action("finish", {})]),
        executor=TrustedLocalExecutor(),
        approval=AutoApproveGateway(),
        report_dir=tmp_path / "report",
    )
    assert outcome.status == "failed"
    assert outcome.failure_analysis


async def test_test_tampering_rejected(tmp_path):
    source = materialize_fixture("paginate", tmp_path / "source")
    fx = load_fixture("paginate")
    tamper_diff = (
        "--- a/tests/test_paginate.py\n"
        "+++ b/tests/test_paginate.py\n"
        "@@ -1,9 +1,2 @@\n"
        "-from shop.paginate import paginate\n"
        "-\n"
        "-\n"
        "-def test_first_page():\n"
        "-    assert paginate([1, 2, 3, 4, 5], 1, 2) == [1, 2]\n"
        "-\n"
        "-\n"
        "-def test_second_page():\n"
        "-    assert paginate([1, 2, 3, 4, 5], 2, 2) == [3, 4]\n"
        "+def test_noop():\n"
        "+    assert True\n"
    )
    outcome = await run_repair(
        RepairTask(repo=str(source), issue=fx.meta["issue"], eval_dir=fx.eval_dir),
        provider=ScriptedMock([action("apply_patch", {"diff": tamper_diff}), action("finish", {})]),
        executor=TrustedLocalExecutor(),
        approval=AutoApproveGateway(),
        report_dir=tmp_path / "report",
    )
    assert outcome.status != "verified"
    assert any(c.name == "tests_untouched" and not c.passed for c in outcome.verification.checks)


async def test_tool_names_restricts_registry(tmp_path):
    source = materialize_fixture("paginate", tmp_path / "source")
    fx = load_fixture("paginate")
    outcome = await run_repair(
        RepairTask(
            repo=str(source),
            issue=fx.meta["issue"],
            eval_dir=fx.eval_dir,
            tool_names=["read_file", "apply_patch", "run_tests"],
        ),
        provider=ScriptedMock([action("search_code", {"pattern": "x"}), action("finish", {})]),
        executor=TrustedLocalExecutor(),
        approval=AutoApproveGateway(),
        report_dir=tmp_path / "report",
    )
    assert outcome.status != "verified"
    events = (tmp_path / "report" / "events.jsonl").read_text(encoding="utf-8")
    assert "unknown tool: search_code" in events


async def test_failed_trusted_prep_is_explicit(tmp_path):
    """Prep failure must abort loudly, not silently poison downstream steps."""
    import pytest

    from safefix.runtime.executor import ExecResult

    class FailingPrepExecutor(TrustedLocalExecutor):
        async def run_trusted_prep(self, command, *, cwd, timeout):
            return ExecResult(exit_code=1, stderr="pip: permission denied")

    source = materialize_fixture("paginate", tmp_path / "source")
    fx = load_fixture("paginate")
    with pytest.raises(RuntimeError, match="preparation failed"):
        await run_repair(
            RepairTask(
                repo=str(source),
                issue=fx.meta["issue"],
                setup_commands=["pip install pytest"],
            ),
            provider=ScriptedMock([action("finish", {})]),
            executor=FailingPrepExecutor(),
            approval=AutoApproveGateway(),
            report_dir=tmp_path / "report",
        )


async def test_runner_error_stops_before_model_call(tmp_path):
    from safefix.runtime.executor import ExecResult

    class BrokenRunner(TrustedLocalExecutor):
        async def run(self, command, *, cwd, timeout):
            return ExecResult(exit_code=1, stderr="python: No module named pytest")

    source = materialize_fixture("paginate", tmp_path / "source")
    report = tmp_path / "report"
    outcome = await run_repair(
        RepairTask(repo=str(source), issue="Fix pagination"),
        provider=ScriptedMock(make_responses()),
        executor=BrokenRunner(),
        approval=AutoApproveGateway(),
        report_dir=report,
    )
    assert outcome.status == "failed"
    assert outcome.llm_calls == 0
    assert outcome.repro_before.classification == "runner_error"
    assert "No module named pytest" in (report / "outcome.json").read_text(encoding="utf-8")
    assert (report / "patch.diff").read_bytes() == b""


async def test_verification_runs_delivered_patch_in_a_separate_workspace(tmp_path):
    class RecordingExecutor(TrustedLocalExecutor):
        def __init__(self):
            super().__init__()
            self.workspaces = []

        async def run(self, command, *, cwd, timeout):
            self.workspaces.append(cwd)
            return await super().run(command, cwd=cwd, timeout=timeout)

    source = materialize_fixture("paginate", tmp_path / "source")
    executor = RecordingExecutor()
    outcome = await run_repair(
        RepairTask(repo=str(source), issue="Fix pagination"),
        provider=ScriptedMock(make_responses()),
        executor=executor,
        approval=AutoApproveGateway(),
        report_dir=tmp_path / "report",
    )
    assert outcome.status == "verified"
    assert len(set(executor.workspaces)) == 2
    assert executor.workspaces[-1] != executor.workspaces[0]
    assert any(c.name == "patch_applied_cleanly" and c.passed for c in outcome.verification.checks)


async def test_bad_export_is_not_verified_even_if_agent_workspace_was_fixed(tmp_path, monkeypatch):
    from safefix.repair import workflow

    async def broken_export(*args, **kwargs):
        return 0, "corrupted diff\n", ""

    monkeypatch.setattr(workflow, "full_candidate_diff", broken_export)
    source = materialize_fixture("paginate", tmp_path / "source")
    outcome = await run_repair(
        RepairTask(repo=str(source), issue="Fix pagination"),
        provider=ScriptedMock(make_responses()),
        executor=TrustedLocalExecutor(),
        approval=AutoApproveGateway(),
        report_dir=tmp_path / "report",
    )
    assert outcome.status == "unverified"
    assert [c.name for c in outcome.verification.checks if not c.passed] == ["patch_applied_cleanly"]
    assert (tmp_path / "report" / "patch.diff").read_bytes() == b"corrupted diff\n"
