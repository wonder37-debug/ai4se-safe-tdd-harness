"""apply_patch: minimal unified-diff editing (pure Python, offline-testable)."""

import pytest

from safefix.models import Action
from safefix.tools.patch import ApplyPatchTool
from safefix.tools.registry import ToolContext, ToolRegistry


@pytest.fixture
def ws(tmp_path):
    (tmp_path / "app.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    return tmp_path


async def apply(ws, diff):
    reg = ToolRegistry([ApplyPatchTool()])
    return await reg.dispatch(Action(tool="apply_patch", args={"diff": diff}), ToolContext(workspace=ws))


MODIFY = """--- a/app.py
+++ b/app.py
@@ -1,2 +1,2 @@
 def add(a, b):
-    return a - b
+    return a + b
"""


async def test_modify_single_hunk(ws):
    obs = await apply(ws, MODIFY)
    assert obs.ok, obs.error
    assert (ws / "app.py").read_text(encoding="utf-8") == "def add(a, b):\n    return a + b\n"


async def test_create_new_file(ws):
    diff = """--- /dev/null
+++ b/util.py
@@ -0,0 +1,2 @@
+def helper():
+    return 42
"""
    obs = await apply(ws, diff)
    assert obs.ok, obs.error
    assert (ws / "util.py").read_text(encoding="utf-8").startswith("def helper")


async def test_context_mismatch_rejected_and_file_unchanged(ws):
    diff = """--- a/app.py
+++ b/app.py
@@ -1,2 +1,2 @@
 def add(a, b):
-    return a * b
+    return a + b
"""
    obs = await apply(ws, diff)
    assert not obs.ok and "context" in obs.error.lower()
    assert "a - b" in (ws / "app.py").read_text(encoding="utf-8")


async def test_multi_file_patch(ws):
    (ws / "other.py").write_text("x = 1\n", encoding="utf-8")
    diff = (
        MODIFY
        + """--- a/other.py
+++ b/other.py
@@ -1 +1 @@
-x = 1
+x = 2
"""
    )
    obs = await apply(ws, diff)
    assert obs.ok, obs.error
    assert "x = 2" in (ws / "other.py").read_text(encoding="utf-8")
    assert "a + b" in (ws / "app.py").read_text(encoding="utf-8")


async def test_path_escape_in_diff_rejected(ws):
    diff = """--- a/../evil.py
+++ b/../evil.py
@@ -0,0 +1 @@
+pwned
"""
    obs = await apply(ws, diff)
    assert not obs.ok and "escapes workspace" in obs.error


async def test_delete_file(ws):
    diff = """--- a/app.py
+++ /dev/null
@@ -1,2 +0,0 @@
-def add(a, b):
-    return a - b
"""
    obs = await apply(ws, diff)
    assert obs.ok, obs.error
    assert not (ws / "app.py").exists()


async def test_hunk_offset_search(ws):
    # prepend lines so the hunk's declared line numbers are stale; applier must search
    (ws / "app.py").write_text("# header\n# header2\ndef add(a, b):\n    return a - b\n", encoding="utf-8")
    obs = await apply(ws, MODIFY)
    assert obs.ok, obs.error
    assert "a + b" in (ws / "app.py").read_text(encoding="utf-8")


async def test_malformed_diff_rejected(ws):
    obs = await apply(ws, "this is not a diff")
    assert not obs.ok


async def test_patch_invalidates_stale_bytecode_cache(ws):
    # Regression: same-second mtime + coincidentally equal size made Python
    # reuse a stale .pyc after patching, so re-tests ran the OLD code.
    cache = ws / "__pycache__"
    cache.mkdir()
    (cache / "app.cpython-312.pyc").write_bytes(b"stale")
    obs = await apply(ws, MODIFY)
    assert obs.ok, obs.error
    assert not cache.exists()
