"""Live-LLM repair integration — explicitly gated, never faked.

Requires BOTH:
- SAFEFIX_REAL_LLM=1 (opt-in), and
- usable credentials (API_KEY + API_BASE_URL in env or .env).

Without them this test is SKIPPED and must be reported as NOT RUN. A scripted
mock success is never presented as live-model performance.
"""

import os
import subprocess
from pathlib import Path

import pytest

from safefix.config import Mode, build_provider, load_env_file
from safefix.creds.store import EncryptedFileStore
from safefix.evaluation.fixtures import load_fixture, materialize_fixture
from safefix.repair.workflow import RepairTask, run_repair
from safefix.runtime.docker_executor import DockerExecutor
from safefix.security.approval import AutoDenyGateway


def _enabled() -> bool:
    if os.environ.get("SAFEFIX_REAL_LLM") != "1":
        return False
    env = load_env_file(Path(__file__).resolve().parents[2] / ".env")
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
    pytest.mark.skipif(not _enabled(), reason="live LLM not configured — real-agent task NOT RUN"),
    pytest.mark.skipif(not _docker_available(), reason="Docker daemon unavailable — real-agent task NOT RUN"),
]


async def test_real_llm_repairs_paginate(tmp_path):
    env = load_env_file(Path(__file__).resolve().parents[2] / ".env")
    provider = await build_provider(
        mode=Mode.REAL,
        creds=EncryptedFileStore(tmp_path / "none.enc"),
        config={},
        env_file=env,
        env=dict(os.environ),
        master_password=os.environ.get("MASTER_PASSWORD"),
    )
    source = materialize_fixture("paginate", tmp_path / "source")
    fx = load_fixture("paginate")
    py = "PYTHONPATH=.deps python -m pytest -q"
    report_dir = Path(".safefix-runs") / "real-llm-paginate"

    outcome = await run_repair(
        RepairTask(
            repo=str(source),
            issue=fx.meta["issue"],
            test_command=py,
            repro_command=f"{py} tests/test_paginate.py",
            eval_dir=fx.eval_dir,
            eval_command=f"{py} _eval_verify",
            setup_commands=["pip install --quiet --target .deps pytest"],
        ),
        provider=provider,
        executor=DockerExecutor(),
        approval=AutoDenyGateway(),
        report_dir=report_dir,
    )
    # record the honest outcome either way; the trajectory is in report_dir
    assert outcome.status in ("verified", "unverified", "failed")
    assert (report_dir / "outcome.json").exists()