"""P2 regression: multi-hunk patches must track cumulative line offsets
(review 4663355641). With repeated context blocks, a later hunk must not be
silently applied to the FIRST occurrence after an earlier hunk shifted lines.
"""

import difflib

from safefix.models import Action
from safefix.tools.patch import ApplyPatchTool
from safefix.tools.registry import ToolContext, ToolRegistry

BLOCK = "def f():\n    return 1\n"


async def apply(ws, diff):
    reg = ToolRegistry([ApplyPatchTool()])
    return await reg.dispatch(Action(tool="apply_patch", args={"diff": diff}), ToolContext(workspace=ws))


async def test_second_duplicate_block_modified_after_prepend(tmp_path):
    original = BLOCK + "\n" + BLOCK  # two identical blocks
    target = "# new header line\n" * 5 + BLOCK + "\n" + BLOCK.replace("return 1", "return 2")
    diff = "".join(
        difflib.unified_diff(
            original.splitlines(keepends=True), target.splitlines(keepends=True), "a/m.py", "b/m.py", n=1
        )
    )
    (tmp_path / "m.py").write_text(original, encoding="utf-8")
    obs = await apply(tmp_path, diff)
    assert obs.ok, obs.error
    result = (tmp_path / "m.py").read_text(encoding="utf-8")
    assert result == target, f"patch applied to wrong block:\n{result}"


async def test_monotonic_hunks_with_deletion_offset(tmp_path):
    original = "keep\n" + BLOCK + "\n" + BLOCK
    target = "keep\n" + BLOCK.replace("return 1", "return 9") + BLOCK
    # first hunk deletes the blank separator line; second hunk targets block 2
    diff = "".join(
        difflib.unified_diff(
            original.splitlines(keepends=True), target.splitlines(keepends=True), "a/m.py", "b/m.py", n=1
        )
    )
    (tmp_path / "m.py").write_text(original, encoding="utf-8")
    obs = await apply(tmp_path, diff)
    assert obs.ok, obs.error
    assert (tmp_path / "m.py").read_text(encoding="utf-8") == target
