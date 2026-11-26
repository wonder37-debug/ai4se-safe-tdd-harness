"""Replay the published fix for more-itertools #1304 on its original base.

Requires Git and pytest. Clones one pinned public repository and runs its Python
tests locally. The repair is scripted from the upstream diff; no API key is used.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

from safefix.llm.mock import ScriptedMock
from safefix.repair.workflow import RepairTask, run_repair
from safefix.runtime.local_executor import LocalTrustedExecutor
from safefix.security.approval import AutoDenyGateway

REPO = "https://github.com/more-itertools/more-itertools.git"
BASE = "790bb0bb2c03e7a07282e5f16f4b1fde35b8fcf5"
FIX = "1ea82a711c69f590054987b5cb194157f8ce8ac4"

REPRO_TEST = """import pytest
from more_itertools import ichunked


def test_nonempty_source_with_zero_chunk_size():
    assert list(ichunked([1, 2, 3], 0)) == []


def test_negative_chunk_size_error():
    with pytest.raises(ValueError, match="n must be at least 0"):
        list(ichunked([1, 2, 3], -1))
"""

EXTRA_TEST = """from more_itertools import ichunked


def test_zero_chunk_size_preserves_source():
    source = iter([5, 6, 7])
    assert list(ichunked(source, 0)) == []
    assert list(source) == [5, 6, 7]


def test_positive_chunk_size_handles_partial_chunk():
    assert [list(part) for part in ichunked([1, 2, 3], 2)] == [[1, 2], [3]]
"""


def git(path: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=path, check=True, capture_output=True, text=True, timeout=180
    ).stdout


async def replay(report_dir: Path) -> None:
    with TemporaryDirectory(prefix="safefix-upstream-") as directory:
        root = Path(directory)
        git(root, "clone", "--quiet", "--no-checkout", REPO, "source")
        source = root / "source"
        git(source, "checkout", "--quiet", "--detach", BASE)
        diff = git(source, "diff", BASE, FIX, "--", "more_itertools/more.py")
        (source / "tests" / "test_issue_1304.py").write_text(REPRO_TEST, encoding="utf-8")
        git(source, "add", "tests/test_issue_1304.py")
        git(
            source,
            "-c",
            "user.name=SafeFix Example",
            "-c",
            "user.email=example@example.invalid",
            "commit",
            "--quiet",
            "-m",
            "Add explicit pytest reproduction for issue #1304",
        )
        hidden_tests = root / "eval"
        hidden_tests.mkdir()
        (hidden_tests / "test_ichunked_replay.py").write_text(EXTRA_TEST, encoding="utf-8")

        actions = [
            {"tool": "apply_patch", "args": {"diff": diff}},
            {"tool": "finish", "args": {}},
        ]
        result = await run_repair(
            RepairTask(
                repo=str(source),
                issue="Make ichunked handle zero and negative chunk sizes consistently with chunked.",
                test_command="python -m pytest -q -p no:asyncio",
                repro_command="python -m pytest -q -p no:asyncio tests/test_issue_1304.py",
                eval_dir=hidden_tests,
                eval_command="python -m pytest -q -p no:asyncio _eval_verify",
            ),
            provider=ScriptedMock([f"```action\n{json.dumps(action)}\n```" for action in actions]),
            executor=LocalTrustedExecutor(),
            approval=AutoDenyGateway(),
            report_dir=report_dir,
        )
        print("Mode: scripted replay of the published upstream fix")
        print(f"Upstream base: {BASE}; suite base: {result.base_commit}")
        print(f"Baseline: {result.repro_before.classification if result.repro_before else 'unknown'}")
        print(f"Result: {result.status}")
        for check in result.verification.checks:
            print(f"  {check.name}: {'PASS' if check.passed else 'FAIL'}")
        print(f"Evidence: {report_dir / 'outcome.json'}")
        if result.status != "verified":
            raise SystemExit(result.failure_analysis)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path(".safefix-runs/more-itertools-1304"))
    asyncio.run(replay(parser.parse_args().out))
