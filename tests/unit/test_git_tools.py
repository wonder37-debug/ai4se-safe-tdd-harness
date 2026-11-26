"""git_status / git_diff tools: fixed argv host git on the isolated workspace.

These are trusted operations (no model-controlled shell string), run against the
disposable copy — never the user's original repository.
"""

import subprocess

import pytest

from safefix.models import Action
from safefix.tools.git import GitDiffTool, GitStatusTool
from safefix.tools.registry import ToolContext, ToolRegistry


def git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path):
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "user.email", "test@example.com")
    git(tmp_path, "config", "user.name", "Test")
    (tmp_path / "app.py").write_text("x = 1\n", encoding="utf-8")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-qm", "init")
    return tmp_path


async def dispatch(tool, ws):
    reg = ToolRegistry([GitStatusTool(), GitDiffTool()])
    return await reg.dispatch(Action(tool=tool, args={}), ToolContext(workspace=ws))


async def test_status_clean(repo):
    obs = await dispatch("git_status", repo)
    assert obs.ok and "clean" in obs.content.lower()


async def test_status_shows_modification(repo):
    (repo / "app.py").write_text("x = 2\n", encoding="utf-8")
    obs = await dispatch("git_status", repo)
    assert obs.ok and "app.py" in obs.content


async def test_diff_shows_change(repo):
    (repo / "app.py").write_text("x = 2\n", encoding="utf-8")
    obs = await dispatch("git_diff", repo)
    assert obs.ok and "-x = 1" in obs.content and "+x = 2" in obs.content


async def test_diff_empty_when_clean(repo):
    obs = await dispatch("git_diff", repo)
    assert obs.ok and obs.content.strip() == ""


async def test_not_a_repo_descriptive_error(tmp_path):
    obs = await dispatch("git_status", tmp_path)
    assert not obs.ok and obs.error
