"""Deterministic mechanism demo: guardrail denial + feedback loop + verified repair.

Runs with NO network and NO subprocess execution (DemoExecutor simulates pytest
outcomes from workspace content). This is the SafeFix equivalent of the legacy
mechanism-demo, upgraded with independent verification.
"""

from safefix.evaluation.fixtures import load_fixture, materialize_fixture
from safefix.llm.demo import demo_responses
from safefix.llm.mock import ScriptedMock
from safefix.repair.workflow import RepairTask, run_repair
from safefix.runtime.demo_executor import DemoExecutor
from safefix.security.approval import AutoDenyGateway


async def test_demo_executor_simulates_failure_then_pass(tmp_path):
    repo = materialize_fixture("paginate", tmp_path / "repo")
    ex = DemoExecutor()
    fail = await ex.run("python -m pytest -q", cwd=repo, timeout=10)
    assert fail.exit_code == 1 and "FAILED" in fail.stdout

    impl = repo / "shop" / "paginate.py"
    impl.write_text(
        impl.read_text(encoding="utf-8").replace("page * size", "(page - 1) * size"), encoding="utf-8"
    )
    ok = await ex.run("python -m pytest -q", cwd=repo, timeout=10)
    assert ok.exit_code == 0 and "passed" in ok.stdout


async def test_full_demo_verified_with_guardrail_denial(tmp_path):
    source = materialize_fixture("paginate", tmp_path / "source")
    fx = load_fixture("paginate")
    report_dir = tmp_path / "demo-report"
    outcome = await run_repair(
        RepairTask(repo=str(source), issue=fx.meta["issue"], eval_dir=fx.eval_dir),
        provider=ScriptedMock(demo_responses()),
        executor=DemoExecutor(),
        approval=AutoDenyGateway(),
        report_dir=report_dir,
    )
    assert outcome.status == "verified", outcome.failure_analysis
    events = (report_dir / "events.jsonl").read_text(encoding="utf-8")
    assert "approval_decision" in events and '"deny"' in events
    assert "DENIED" in events
    assert "(page - 1) * size" in outcome.patch
