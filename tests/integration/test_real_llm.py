"""Live-LLM ACCEPTANCE tests — explicitly gated, never faked.

Layering (review requirement):
- L1 API connectivity + native tool calling + fallback + usage: examples/real_smoke.py
- L2 real model-generated tool calls inside the loop: asserted here via events/usage
- L3 independently verified repair: these tests REQUIRE status == "verified";
  a finish claim, an unverified patch, or a failure never passes.

Requires BOTH:
- SAFEFIX_REAL_LLM=1 (opt-in), and
- usable credentials (API_KEY + API_BASE_URL in env or .env).

Without them these tests are SKIPPED and must be reported as NOT RUN.
On failure the full evidence (outcome.json / events.jsonl / patch.diff) is
preserved in the report directory; assertions are never weakened to pass.
"""

import json
import os
import subprocess
from pathlib import Path

import pytest

from safefix.agent.state import Budgets
from safefix.config import Mode, build_provider, load_env_file
from safefix.creds.store import EncryptedFileStore
from safefix.evaluation.fixtures import load_fixture, materialize_fixture
from safefix.repair.workflow import RepairTask, run_repair
from safefix.runtime.docker_executor import DockerExecutor
from safefix.security.approval import AutoDenyGateway

REPO_ROOT = Path(__file__).resolve().parents[2]


def _enabled() -> bool:
    if os.environ.get("SAFEFIX_REAL_LLM") != "1":
        return False
    env = load_env_file(REPO_ROOT / ".env")
    key = os.environ.get("API_KEY") or env.get("API_KEY")
    base = os.environ.get("API_BASE_URL") or env.get("API_BASE_URL")
    return bool(key and base)


def _docker_available() -> bool:
    try:
        subprocess.run(["docker", "info"], capture_output=True, timeout=20, check=True)
        return True
    except (OSError, subprocess.SubprocessError):
        return False


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not _enabled(), reason="live LLM not configured — real-agent acceptance NOT RUN"),
    pytest.mark.skipif(
        not _docker_available(), reason="Docker daemon unavailable — real-agent acceptance NOT RUN"
    ),
]


async def _run_real(fixture_name: str, report_dir: Path):
    env = load_env_file(REPO_ROOT / ".env")
    provider = await build_provider(
        mode=Mode.REAL,
        creds=EncryptedFileStore(report_dir / "absent.enc"),
        config={},
        env_file=env,
        env=dict(os.environ),
        master_password=os.environ.get("MASTER_PASSWORD"),
    )
    source = materialize_fixture(fixture_name, report_dir.parent / f"{fixture_name}-source")
    fx = load_fixture(fixture_name)
    py = "PYTHONPATH=.deps python -m pytest -q"
    outcome = await run_repair(
        RepairTask(
            repo=str(source),
            issue=fx.meta["issue"],
            test_command=py,
            repro_command=f"{py} {fx.meta['repro_command'].split('pytest -q ')[-1]}",
            eval_dir=fx.eval_dir,
            eval_command=f"{py} _eval_verify",
            setup_commands=["pip install --quiet --target .deps pytest"],
            budgets=Budgets(max_llm_calls=12, max_wall_seconds=420),
        ),
        provider=provider,
        executor=DockerExecutor(),
        approval=AutoDenyGateway(),
        report_dir=report_dir,
    )
    # L2 evidence: real calls, real token usage, real model-generated tool actions
    assert outcome.llm_calls > 0, "no real LLM calls occurred"
    assert outcome.usage.total_tokens > 0, "no token usage recorded"
    events = [
        json.loads(line) for line in (report_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    tools = [e["payload"].get("tool") for e in events if e["type"] == "action"]
    assert any(t not in (None, "finish") for t in tools), f"no real tool calls: {tools}"
    # original repository untouched
    status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=source, capture_output=True, text=True, check=True
    ).stdout
    assert status.strip() == "", "original repository was modified"
    return outcome


async def test_real_repair_paginate_must_verify(tmp_path):
    outcome = await _run_real("paginate", tmp_path / "real-paginate")
    assert outcome.status == "verified", (
        f"real repair NOT verified: {outcome.failure_analysis}; evidence: {tmp_path / 'real-paginate'}"
    )
    assert outcome.repro_before is not None and not outcome.repro_before.passed
    assert "(page - 1) * size" in outcome.patch


async def test_real_repair_heldout_querystring_must_verify(tmp_path):
    outcome = await _run_real("querystring", tmp_path / "real-querystring")
    assert outcome.status == "verified", (
        f"held-out real repair NOT verified: {outcome.failure_analysis}; evidence: {tmp_path / 'real-querystring'}"
    )
    assert outcome.repro_before is not None and not outcome.repro_before.passed
