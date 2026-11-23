"""P1 regressions: search_code symlink fence (4661696747) and killable regex
timeout (4663423540). Host file contents must never leak through search, and a
catastrophic-backtracking pattern must not hang the event loop.
"""

import os
import time

import pytest

from safefix.models import Action
from safefix.tools.files import SearchCodeTool
from safefix.tools.registry import ToolContext, ToolRegistry


async def search(ws, pattern, **kw):
    reg = ToolRegistry([SearchCodeTool()])
    return await reg.dispatch(
        Action(tool="search_code", args={"pattern": pattern, **kw}), ToolContext(workspace=ws)
    )


async def test_search_does_not_leak_external_symlink_target(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("API_KEY=sk-leaked-canary\n", encoding="utf-8")
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "ok.py").write_text("needle = 1\n", encoding="utf-8")
    try:
        os.symlink(outside / "secret.txt", ws / "link.txt")
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation not permitted on this host")
    obs = await search(ws, "sk-leaked-canary")
    assert obs.ok
    assert "sk-leaked-canary" not in obs.content
    assert "API_KEY" not in obs.content


async def test_search_catastrophic_regex_is_terminated(tmp_path):
    (tmp_path / "bomb.txt").write_text("a" * 40 + "!\n", encoding="utf-8")
    start = time.monotonic()
    obs = await search(tmp_path, r"(a+)+$", timeout=1.0)
    elapsed = time.monotonic() - start
    assert elapsed < 8, f"search hung for {elapsed:.1f}s"
    # either killed with an explicit timeout error, or finished without matches
    assert (not obs.ok and "timed out" in obs.error.lower()) or obs.ok


async def test_search_normal_case_still_works(tmp_path):
    (tmp_path / "app.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    obs = await search(tmp_path, r"def add")
    assert obs.ok and "app.py:1" in obs.content


async def test_search_invalid_regex_fast_error(tmp_path):
    obs = await search(tmp_path, "(")
    assert not obs.ok and "regex" in obs.error.lower()
