"""Round-4 regressions: ignore-rule-independent protected-file enumeration
(4665404091) and non-regular-file read refusal (4665404099).
"""

import os
import subprocess

import pytest

from safefix.models import Action
from safefix.repair.verifier import verify_patch
from safefix.runtime.executor import ExecResult
from safefix.runtime.workspace import cleanup_workspace, prepare_workspace
from safefix.tools.files import ReadFileTool
from safefix.tools.git import full_candidate_diff
from safefix.tools.registry import ToolContext, ToolRegistry


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


async def test_gitignore_cannot_hide_protected_conftest(tmp_path):
    repo = make_repo(tmp_path, {"app.py": "def value():\n    return 0\n"})
    ws = prepare_workspace(str(repo), dest=tmp_path / "ws")
    try:
        # agent hides a pytest hook behind a .gitignore entry
        (ws.path / ".gitignore").write_text("conftest.py\n", encoding="utf-8")
        (ws.path / "conftest.py").write_text(
            "def pytest_collection_modifyitems(config, items):\n    items[:] = []\n", encoding="utf-8"
        )
        rc, diff, _ = await full_candidate_diff(ws.path, ws.git_dir)
        assert rc == 0
        assert "conftest.py" in diff, "hidden hook must still be exported in the patch"
        report = await verify_patch(
            ws.path,
            executor=PassingExecutor(),
            test_command="python -m pytest -q",
            repro_command=None,
            eval_dir=None,
            git_dir=ws.git_dir,
        )
        assert any(c.name == "tests_untouched" and not c.passed for c in report.checks), (
            "ignore rules must not exempt protected files from tamper checks"
        )
    finally:
        cleanup_workspace(ws)


async def test_read_file_refuses_fifo(tmp_path):
    if not hasattr(os, "mkfifo"):
        pytest.skip("mkfifo not available on this host")
    fifo = tmp_path / "pipe"
    os.mkfifo(fifo)
    reg = ToolRegistry([ReadFileTool()])
    obs = await reg.dispatch(Action(tool="read_file", args={"path": "pipe"}), ToolContext(workspace=tmp_path))
    assert not obs.ok
    assert "regular file" in obs.error
