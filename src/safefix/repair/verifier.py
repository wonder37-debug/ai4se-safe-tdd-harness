"""Independent success verification — evidence, not claims.

A ``finish`` action alone never means success. This module re-checks, AFTER the
agent has halted, that:
- the patch is non-empty;
- no existing test file was modified/deleted/renamed (anti-tampering);
- the reproduction command now passes;
- the full regression command passes;
- the independent evaluation tests (kept outside the agent workspace during
  generation) pass against the patched code.
"""

from __future__ import annotations

import shutil
from pathlib import Path, PurePosixPath

from pydantic import BaseModel, Field

from safefix.runtime.executor import ExecutionBackend
from safefix.tools.git import _git

_VERIFY_TIMEOUT = 300.0


class CheckResult(BaseModel):
    name: str
    passed: bool
    detail: str = ""


class VerificationReport(BaseModel):
    checks: list[CheckResult] = Field(default_factory=list)

    @property
    def verified(self) -> bool:
        return bool(self.checks) and all(c.passed for c in self.checks)


def _is_test_path(rel: str) -> bool:
    parts = PurePosixPath(rel).parts
    if not parts:
        return False
    name = parts[-1]
    return (
        any(p in ("tests", "test") for p in parts[:-1])
        or name.startswith("test_")
        or name.endswith("_test.py")
        or name == "conftest.py"
    )


def _tail(result, n: int = 400) -> str:
    return (result.stdout + result.stderr)[-n:]


async def verify_patch(
    workspace: Path,
    *,
    executor: ExecutionBackend,
    test_command: str,
    repro_command: str | None,
    eval_dir: Path | None,
) -> VerificationReport:
    checks: list[CheckResult] = []

    _, diff, _ = await _git(workspace, "diff")
    checks.append(CheckResult(name="patch_nonempty", passed=bool(diff.strip()), detail="working-tree diff vs HEAD"))

    _, name_status, _ = await _git(workspace, "diff", "--name-status")
    tampered = []
    for line in name_status.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2 and parts[0][:1] in ("M", "D", "R") and _is_test_path(parts[-1]):
            tampered.append(line)
    checks.append(
        CheckResult(
            name="tests_untouched",
            passed=not tampered,
            detail="; ".join(tampered) if tampered else "no existing test files modified/deleted",
        )
    )

    repro_cmd = repro_command or test_command
    repro = await executor.run(repro_cmd, cwd=workspace, timeout=_VERIFY_TIMEOUT)
    checks.append(
        CheckResult(name="repro_passes", passed=repro.exit_code == 0 and not repro.timed_out, detail=_tail(repro))
    )

    regression = await executor.run(test_command, cwd=workspace, timeout=_VERIFY_TIMEOUT)
    checks.append(
        CheckResult(
            name="regression_passes", passed=regression.exit_code == 0 and not regression.timed_out, detail=_tail(regression)
        )
    )

    if eval_dir is not None:
        eval_copy = workspace / "_eval_verify"
        shutil.copytree(eval_dir, eval_copy)
        try:
            eval_res = await executor.run(
                "python -m pytest -q _eval_verify", cwd=workspace, timeout=_VERIFY_TIMEOUT
            )
            checks.append(
                CheckResult(
                    name="eval_passes", passed=eval_res.exit_code == 0 and not eval_res.timed_out, detail=_tail(eval_res)
                )
            )
        finally:
            shutil.rmtree(eval_copy, ignore_errors=True)

    return VerificationReport(checks=checks)