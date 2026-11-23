"""Disposable workspace: clone isolation, base commit recording, cleanup."""

import subprocess

import pytest

from safefix.runtime.workspace import WorkspaceError, cleanup_workspace, prepare_workspace


def git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def source_repo(tmp_path):
    repo = tmp_path / "source"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "t@t")
    git(repo, "config", "user.name", "T")
    (repo / "app.py").write_text("x = 1\n", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "base")
    return repo


def test_prepare_clones_and_records_base_commit(source_repo, tmp_path):
    ws = prepare_workspace(str(source_repo), dest=tmp_path / "ws")
    try:
        assert ws.base_commit
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=source_repo, capture_output=True, text=True, check=True
        ).stdout.strip()
        assert ws.base_commit == head
        assert (ws.path / "app.py").exists()
    finally:
        cleanup_workspace(ws)


def test_workspace_is_isolated_from_source(source_repo, tmp_path):
    ws = prepare_workspace(str(source_repo), dest=tmp_path / "ws")
    try:
        (ws.path / "app.py").write_text("x = 999\n", encoding="utf-8")
        assert (source_repo / "app.py").read_text(encoding="utf-8") == "x = 1\n"
        status = subprocess.run(
            ["git", "status", "--porcelain"], cwd=source_repo, capture_output=True, text=True, check=True
        ).stdout
        assert status.strip() == ""
    finally:
        cleanup_workspace(ws)


def test_cleanup_removes_workspace(source_repo, tmp_path):
    ws = prepare_workspace(str(source_repo), dest=tmp_path / "ws")
    cleanup_workspace(ws)
    assert not ws.path.exists()


def test_non_repo_directory_rejected(tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()
    with pytest.raises(WorkspaceError):
        prepare_workspace(str(plain), dest=tmp_path / "ws")