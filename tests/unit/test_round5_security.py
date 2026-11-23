"""Round-5 regressions: raw NUL paths for tamper checks (4665584602),
raw untracked paths for export (4665584617), applicable binary diffs (4665584631).
"""

import subprocess

from safefix.repair.verifier import verify_patch
from safefix.runtime.executor import ExecResult
from safefix.runtime.workspace import cleanup_workspace, prepare_workspace
from safefix.tools.git import full_candidate_diff


def git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def make_repo(tmp_path, files: dict):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "t@t")
    git(repo, "config", "user.name", "T")
    for rel, content in files.items():
        p = repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            p.write_bytes(content)
        else:
            p.write_text(content, encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "base")
    return repo


class PassingExecutor:
    async def run(self, command, *, cwd, timeout):
        return ExecResult(stdout="2 passed", exit_code=0)


async def test_non_ascii_test_config_path_still_protected(tmp_path):
    repo = make_repo(tmp_path, {"中文/conftest.py": "# hook\n", "app.py": "x = 1\n"})
    ws = prepare_workspace(str(repo), dest=tmp_path / "ws")
    try:
        (ws.path / "中文" / "conftest.py").write_text(
            "def pytest_collection_modifyitems(config, items):\n    items[:] = []\n", encoding="utf-8"
        )
        report = await verify_patch(
            ws.path,
            executor=PassingExecutor(),
            test_command="python -m pytest -q",
            repro_command=None,
            eval_dir=None,
            git_dir=ws.git_dir,
        )
        assert any(c.name == "tests_untouched" and not c.passed for c in report.checks), (
            "quoted/escaped non-ASCII path must not bypass protection"
        )
    finally:
        cleanup_workspace(ws)


async def test_non_ascii_new_file_exported(tmp_path):
    repo = make_repo(tmp_path, {"app.py": "x = 1\n"})
    ws = prepare_workspace(str(repo), dest=tmp_path / "ws")
    try:
        (ws.path / "新模块.py").write_text("VALUE = 42\n", encoding="utf-8")
        (ws.path / "app.py").write_text("from 新模块 import VALUE\nx = VALUE\n", encoding="utf-8")
        rc, diff, err = await full_candidate_diff(ws.path, ws.git_dir)
        assert rc == 0, err
        assert "VALUE = 42" in diff
        patch = tmp_path / "candidate.diff"
        patch.write_bytes(diff.encode("utf-8"))
        git(repo, "apply", str(patch))
        assert (repo / "新模块.py").read_text(encoding="utf-8") == "VALUE = 42\n"
    finally:
        cleanup_workspace(ws)


async def test_binary_change_exported_as_applicable_patch(tmp_path):
    repo = make_repo(tmp_path, {"data.bin": b"\x00\x01\x02before"})
    ws = prepare_workspace(str(repo), dest=tmp_path / "ws")
    try:
        (ws.path / "data.bin").write_bytes(b"\x00\x01\x02after")
        rc, diff, err = await full_candidate_diff(ws.path, ws.git_dir)
        assert rc == 0, err
        assert "GIT binary patch" in diff, "binary change must carry applicable data"
        check = subprocess.run(
            ["git", "apply", "--check", "-"],
            cwd=repo,  # base state: the workspace already contains the change
            input=diff.encode("utf-8"),  # raw bytes: text mode corrupts binary patches
            capture_output=True,
        )
        assert check.returncode == 0, f"patch not applicable: {check.stderr.decode('utf-8', 'replace')}"
    finally:
        cleanup_workspace(ws)
