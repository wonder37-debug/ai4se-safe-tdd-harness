"""Round-3 regressions: frozen sanitized git metadata (4665182698/4665182713),
rename both-end tamper check (4665182720), memory symlink fence (4665182703),
truncated-patch refusal (4665182729).
"""

import os
import subprocess
import sys

import pytest

from safefix.memory.store import MemoryStore
from safefix.repair.verifier import verify_patch
from safefix.runtime.executor import ExecResult
from safefix.runtime.workspace import cleanup_workspace, prepare_workspace
from safefix.tools.git import full_candidate_diff


def git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def make_repo(tmp_path, files):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "t@t")
    git(repo, "config", "user.name", "T")
    for rel, content in files.items():
        p = repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "base")
    return repo


class PassingExecutor:
    async def run(self, command, *, cwd, timeout):
        return ExecResult(stdout="2 passed", exit_code=0)


async def test_container_written_filter_driver_not_executed_by_host_git(tmp_path):
    repo = make_repo(tmp_path, {"app.py": "x = 1\n"})
    ws = prepare_workspace(str(repo), dest=tmp_path / "ws")
    try:
        marker = tmp_path / "filter-pwned"
        hook = f"\"{sys.executable}\" -c \"from pathlib import Path; Path(r'{marker}').write_text('x')\""
        # simulate the CONTAINER rewriting the writable mount's git metadata
        git(ws.path, "config", "filter.evil.clean", hook)
        (ws.path / ".gitattributes").write_text("* filter=evil\n", encoding="utf-8")
        (ws.path / "app.py").write_text("x = 2\n", encoding="utf-8")
        rc, diff, err = await full_candidate_diff(ws.path, ws.git_dir)
        assert rc == 0, err
        assert "-x = 1" in diff and "+x = 2" in diff
        assert not marker.exists(), "host git executed a container-planted clean filter"
    finally:
        cleanup_workspace(ws)


async def test_diff_base_frozen_against_container_commits(tmp_path):
    repo = make_repo(
        tmp_path,
        {
            "app.py": "def value():\n    return 0\n",
            "tests/test_app.py": "from app import value\n\n\ndef test_value():\n    assert value() == 42\n",
        },
    )
    ws = prepare_workspace(str(repo), dest=tmp_path / "ws")
    try:
        # container commits a test-weakening change, then leaves a source edit
        (ws.path / "tests" / "test_app.py").write_text(
            "def test_noop():\n    assert True\n", encoding="utf-8"
        )
        git(ws.path, "add", ".")
        git(ws.path, "commit", "-qm", "weaken tests")
        (ws.path / "app.py").write_text("def value():\n    return 42\n", encoding="utf-8")
        rc, diff, _ = await full_candidate_diff(ws.path, ws.git_dir)
        assert rc == 0
        assert "tests/test_app.py" in diff, "committed test tampering hidden by mutable HEAD"
        report = await verify_patch(
            ws.path,
            executor=PassingExecutor(),
            test_command="python -m pytest -q",
            repro_command=None,
            eval_dir=None,
            git_dir=ws.git_dir,
        )
        assert any(c.name == "tests_untouched" and not c.passed for c in report.checks)
    finally:
        cleanup_workspace(ws)


async def test_rename_of_test_file_detected_on_both_ends(tmp_path):
    repo = make_repo(
        tmp_path,
        {
            "app.py": "def value():\n    return 0\n",
            "tests/test_bad.py": "from app import value\n\n\ndef test_value():\n    assert value() == 42\n",
        },
    )
    ws = prepare_workspace(str(repo), dest=tmp_path / "ws")
    try:
        git(ws.path, "mv", "tests/test_bad.py", "helper.py")
        git(ws.path, "commit", "-qm", "move test out of collection")
        report = await verify_patch(
            ws.path,
            executor=PassingExecutor(),
            test_command="python -m pytest -q",
            repro_command=None,
            eval_dir=None,
            git_dir=ws.git_dir,
        )
        assert any(c.name == "tests_untouched" and not c.passed for c in report.checks), (
            "rename source path must be checked"
        )
    finally:
        cleanup_workspace(ws)


async def test_memory_symlink_does_not_leak_into_prompt(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    secret = outside / "canary.md"
    secret.write_text("API_KEY=sk-memory-leak-canary\n", encoding="utf-8")
    mem_dir = tmp_path / "mem"
    mem_dir.mkdir()
    (mem_dir / "ok.md").write_text("safe note", encoding="utf-8")
    try:
        os.symlink(secret, mem_dir / "evil.md")
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation not permitted on this host")
    store = MemoryStore(mem_dir)
    prompt = await store.system_prompt()
    assert "safe note" in prompt
    assert "sk-memory-leak-canary" not in prompt


async def test_truncated_diff_refused_as_patch(tmp_path):
    big = "line\n" * 300_000  # > 1MB diff
    repo = make_repo(tmp_path, {"big.txt": big})
    ws = prepare_workspace(str(repo), dest=tmp_path / "ws")
    try:
        (ws.path / "big.txt").write_text(big.replace("line", "LINE"), encoding="utf-8")
        rc, _, err = await full_candidate_diff(ws.path, ws.git_dir)
        assert rc != 0
        assert "truncated" in err
    finally:
        cleanup_workspace(ws)
