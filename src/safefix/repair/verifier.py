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

import re
import shutil
from pathlib import Path, PurePosixPath

from pydantic import BaseModel, Field

from safefix.runtime.executor import ExecutionBackend
from safefix.tools.git import DIFF_SAFE_ARGS, _git, full_candidate_diff, untracked_files

_VERIFY_TIMEOUT = 300.0

# Test-run configuration is protected like test code: editing pytest.ini /
# pyproject [tool.pytest] / conftest can fake success without fixing anything
# (review 4662992875).
_PROTECTED_CONFIG = {"pytest.ini", "tox.ini", "setup.cfg", "conftest.py", "pyproject.toml"}

# Independent verification overrides workspace pytest config and demands proof
# that tests actually EXECUTED (collect-only returns 0 without running anything).
_TRUSTED_PYTEST_FLAGS = " --override-ini=addopts= -p no:cacheprovider"
_RAN_RE = re.compile(r"\d+ passed")


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
        or name in _PROTECTED_CONFIG
    )


def _tail(result, n: int = 400) -> str:
    return (result.stdout + result.stderr)[-n:]


def _trusted_command(cmd: str) -> str:
    if "pytest" in cmd:
        return cmd + _TRUSTED_PYTEST_FLAGS
    return cmd


def _tests_actually_passed(result) -> bool:
    if result.exit_code != 0 or result.timed_out:
        return False
    output = result.stdout + result.stderr
    if "no tests ran" in output:
        return False
    return bool(_RAN_RE.search(output))


async def verify_patch(
    workspace: Path,
    *,
    executor: ExecutionBackend,
    test_command: str,
    repro_command: str | None,
    eval_dir: Path | None,
    eval_command: str | None = None,
    git_dir: Path | None = None,
) -> VerificationReport:
    checks: list[CheckResult] = []

    _, diff, _ = await full_candidate_diff(workspace, git_dir)
    checks.append(
        CheckResult(
            name="patch_nonempty",
            passed=bool(diff.strip()),
            detail="full candidate change vs HEAD (incl. new files)",
        )
    )

    _, name_status, _ = await _git(
        workspace, "diff", "HEAD", "--name-status", *DIFF_SAFE_ARGS, git_dir=git_dir
    )
    tampered = []
    for line in name_status.splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        status = parts[0][:1]
        # M/D/R/T/C all change test content; T (type change, e.g. file -> symlink
        # to a passing helper) must not bypass the check (review 4664964020).
        # Renames/copies carry BOTH paths: moving a test out of collection is
        # tampering even if the destination looks innocent (review 4665182720).
        paths = parts[1:] if status in ("R", "C") else [parts[-1]]
        if status in ("M", "D", "R", "T", "C") and any(_is_test_path(p) for p in paths):
            tampered.append(line)
    for rel in await untracked_files(workspace, git_dir):
        if _is_test_path(rel):
            tampered.append(f"A\t{rel}")
    checks.append(
        CheckResult(
            name="tests_untouched",
            passed=not tampered,
            detail="; ".join(tampered) if tampered else "no test files/config modified, deleted or added",
        )
    )

    repro_cmd = _trusted_command(repro_command or test_command)
    repro = await executor.run(repro_cmd, cwd=workspace, timeout=_VERIFY_TIMEOUT)
    checks.append(CheckResult(name="repro_passes", passed=_tests_actually_passed(repro), detail=_tail(repro)))

    regression = await executor.run(_trusted_command(test_command), cwd=workspace, timeout=_VERIFY_TIMEOUT)
    checks.append(
        CheckResult(
            name="regression_passes",
            passed=_tests_actually_passed(regression),
            detail=_tail(regression),
        )
    )

    if eval_dir is not None:
        eval_copy = workspace / "_eval_verify"
        shutil.copytree(eval_dir, eval_copy)
        try:
            eval_res = await executor.run(
                _trusted_command(eval_command or "python -m pytest -q _eval_verify"),
                cwd=workspace,
                timeout=_VERIFY_TIMEOUT,
            )
            checks.append(
                CheckResult(
                    name="eval_passes",
                    passed=_tests_actually_passed(eval_res),
                    detail=_tail(eval_res),
                )
            )
        finally:
            shutil.rmtree(eval_copy, ignore_errors=True)

    return VerificationReport(checks=checks)
