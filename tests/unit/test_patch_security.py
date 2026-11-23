"""P1 regression: apply_patch must never touch .git metadata (review 4661696737).

A patch to .git/config (e.g. core.fsmonitor) would make subsequent HOST git
calls execute attacker-controlled commands, bypassing Docker and approval.
"""

from safefix.models import Action
from safefix.tools.files import ReadFileTool
from safefix.tools.patch import ApplyPatchTool
from safefix.tools.registry import ToolContext, ToolRegistry

GIT_CONFIG_PATCH = """--- a/.git/config
+++ b/.git/config
@@ -1,3 +1,4 @@
 [core]
 \trepositoryformatversion = 0
+\tfsmonitor = evil-command
"""


async def test_patch_to_git_config_rejected(tmp_path):
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("[core]\n\trepositoryformatversion = 0\n", encoding="utf-8")
    reg = ToolRegistry([ApplyPatchTool()])
    obs = await reg.dispatch(
        Action(tool="apply_patch", args={"diff": GIT_CONFIG_PATCH}), ToolContext(workspace=tmp_path)
    )
    assert not obs.ok
    assert ".git" in obs.error
    assert "fsmonitor" not in (tmp_path / ".git" / "config").read_text(encoding="utf-8")


async def test_patch_creating_git_hooks_rejected(tmp_path):
    (tmp_path / ".git").mkdir()
    diff = """--- /dev/null
+++ b/.git/hooks/pre-commit
@@ -0,0 +1,2 @@
+#!/bin/sh
+evil
"""
    reg = ToolRegistry([ApplyPatchTool()])
    obs = await reg.dispatch(Action(tool="apply_patch", args={"diff": diff}), ToolContext(workspace=tmp_path))
    assert not obs.ok and ".git" in obs.error
    assert not (tmp_path / ".git" / "hooks").exists()


async def test_read_file_git_metadata_rejected(tmp_path):
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("[core]\n", encoding="utf-8")
    reg = ToolRegistry([ReadFileTool()])
    obs = await reg.dispatch(
        Action(tool="read_file", args={"path": ".git/config"}), ToolContext(workspace=tmp_path)
    )
    assert not obs.ok and ".git" in obs.error


async def test_normal_patch_still_works(tmp_path):
    (tmp_path / "app.py").write_text("x = 1\n", encoding="utf-8")
    diff = """--- a/app.py
+++ b/app.py
@@ -1 +1 @@
-x = 1
+x = 2
"""
    reg = ToolRegistry([ApplyPatchTool()])
    obs = await reg.dispatch(Action(tool="apply_patch", args={"diff": diff}), ToolContext(workspace=tmp_path))
    assert obs.ok, obs.error
