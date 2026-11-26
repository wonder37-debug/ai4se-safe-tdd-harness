"""P1 regression: host git calls must not execute untrusted repo config
(review 4661696737, second half). core.fsmonitor / external diff / textconv /
hooks / system+global config are all disabled for workspace git invocations.
"""

import subprocess
import sys

import pytest

from safefix.models import Action
from safefix.tools.git import GitStatusTool, _git
from safefix.tools.registry import ToolContext, ToolRegistry


def git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path):
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "user.email", "t@t")
    git(tmp_path, "config", "user.name", "T")
    (tmp_path / "app.py").write_text("x = 1\n", encoding="utf-8")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-qm", "base")
    return tmp_path


async def test_git_hardening_flags_and_env(repo, monkeypatch):
    captured = {}
    real_exec = __import__("asyncio").create_subprocess_exec

    async def spy_exec(*args, **kw):
        captured["args"] = args
        captured["env"] = kw.get("env")
        return await real_exec(*args, **kw)

    monkeypatch.setattr("safefix.tools.git.asyncio.create_subprocess_exec", spy_exec)
    rc, _, _ = await _git(repo, "status", "--porcelain")
    assert rc == 0
    args = captured["args"]
    assert "-c" in args and "core.fsmonitor=false" in args
    env = captured["env"]
    assert env is not None and env.get("GIT_TERMINAL_PROMPT") == "0"


async def test_fsmonitor_hook_not_executed(repo, tmp_path):
    marker = tmp_path / "fsmonitor-pwned"
    hook = f"\"{sys.executable}\" -c \"from pathlib import Path; Path(r'{marker}').write_text('x')\""
    git(repo, "config", "core.fsmonitor", hook)
    reg = ToolRegistry([GitStatusTool()])
    obs = await reg.dispatch(Action(tool="git_status", args={}), ToolContext(workspace=repo))
    assert obs.ok, obs.error
    assert not marker.exists(), "host git executed the untrusted fsmonitor hook"


async def test_external_diff_not_executed(repo, tmp_path):
    marker = tmp_path / "extdiff-pwned"
    hook = f"\"{sys.executable}\" -c \"from pathlib import Path; Path(r'{marker}').write_text('x')\""
    git(repo, "config", "diff.external", hook)
    (repo / "app.py").write_text("x = 2\n", encoding="utf-8")
    from safefix.tools.git import GitDiffTool

    reg = ToolRegistry([GitDiffTool()])
    obs = await reg.dispatch(Action(tool="git_diff", args={}), ToolContext(workspace=repo))
    assert obs.ok, obs.error
    assert not marker.exists(), "host git executed the untrusted external diff driver"
    assert "-x = 1" in obs.content and "+x = 2" in obs.content
