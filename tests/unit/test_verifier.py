"""Independent verifier: success requires evidence, not a 'finish' claim."""

import subprocess

import pytest

from safefix.evaluation.fixtures import materialize_fixture
from safefix.runtime.executor import ExecResult
from safefix.repair.verifier import verify_patch


def git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


class RoutingExecutor:
    """Fake executor: exit code decided by command substring (offline, deterministic)."""

    def __init__(self, fail_patterns=()):
        self.fail_patterns = fail_patterns
        self.commands: list[str] = []

    async def run(self, command, *, cwd, timeout):
        self.commands.append(command)
        failed = any(p in command for p in self.fail_patterns)
        return ExecResult(stdout="1 failed" if failed else "all passed", exit_code=1 if failed else 0)


@pytest.fixture
def patched_repo(tmp_path):
    repo = materialize_fixture("paginate", tmp_path / "repo")
    impl = repo / "shop" / "paginate.py"
    impl.write_text(impl.read_text(encoding="utf-8").replace("page * size", "(page - 1) * size"), encoding="utf-8")
    return repo


async def test_valid_patch_verifies(patched_repo, tmp_path):
    fx_eval = tmp_path / "eval"
    fx_eval.mkdir()
    (fx_eval / "test_eval_ok.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    report = await verify_patch(
        patched_repo,
        executor=RoutingExecutor(),
        test_command="python -m pytest -q",
        repro_command="python -m pytest -q tests/test_paginate.py",
        eval_dir=fx_eval,
    )
    assert report.verified
    names = {c.name for c in report.checks}
    assert {"patch_nonempty", "tests_untouched", "repro_passes", "regression_passes", "eval_passes"} <= names


async def test_empty_patch_rejected(tmp_path):
    repo = materialize_fixture("paginate", tmp_path / "repo")
    report = await verify_patch(
        repo, executor=RoutingExecutor(), test_command="python -m pytest -q", repro_command=None, eval_dir=None
    )
    assert not report.verified
    assert any(c.name == "patch_nonempty" and not c.passed for c in report.checks)


async def test_modified_test_file_rejected(patched_repo):
    test_file = patched_repo / "tests" / "test_paginate.py"
    test_file.write_text("def test_weakened():\n    assert True\n", encoding="utf-8")
    report = await verify_patch(
        patched_repo, executor=RoutingExecutor(), test_command="python -m pytest -q", repro_command=None, eval_dir=None
    )
    assert not report.verified
    assert any(c.name == "tests_untouched" and not c.passed for c in report.checks)


async def test_deleted_test_file_rejected(patched_repo):
    (patched_repo / "tests" / "test_paginate.py").unlink()
    report = await verify_patch(
        patched_repo, executor=RoutingExecutor(), test_command="python -m pytest -q", repro_command=None, eval_dir=None
    )
    assert not report.verified


async def test_failing_regression_rejected(patched_repo):
    report = await verify_patch(
        patched_repo,
        executor=RoutingExecutor(fail_patterns=("pytest -q",)),
        test_command="python -m pytest -q",
        repro_command=None,
        eval_dir=None,
    )
    assert not report.verified
    assert any(c.name == "regression_passes" and not c.passed for c in report.checks)


async def test_failing_eval_rejected(patched_repo, tmp_path):
    fx_eval = tmp_path / "eval"
    fx_eval.mkdir()
    (fx_eval / "test_eval_x.py").write_text("def test_x():\n    assert False\n", encoding="utf-8")
    report = await verify_patch(
        patched_repo,
        executor=RoutingExecutor(fail_patterns=("_eval_verify",)),
        test_command="python -m pytest -q",
        repro_command=None,
        eval_dir=fx_eval,
    )
    assert not report.verified
    assert any(c.name == "eval_passes" and not c.passed for c in report.checks)
    # eval copies are cleaned from the workspace afterwards
    assert not (patched_repo / "_eval_verify").exists()