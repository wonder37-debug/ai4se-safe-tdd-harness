"""File tools: workspace fence (incl. symlink escape), truncation, search."""

import os

import pytest

from safefix.models import Action
from safefix.tools.files import ListFilesTool, ReadFileTool, SearchCodeTool
from safefix.tools.registry import ToolContext, ToolRegistry


@pytest.fixture
def workspace(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("hello", encoding="utf-8")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("secret", encoding="utf-8")
    return tmp_path


def registry():
    return ToolRegistry([ReadFileTool(), ListFilesTool(), SearchCodeTool()])


async def dispatch(tool, args, ws):
    return await registry().dispatch(Action(tool=tool, args=args), ToolContext(workspace=ws))


async def test_read_file(workspace):
    obs = await dispatch("read_file", {"path": "src/app.py"}, workspace)
    assert obs.ok and "def add" in obs.content


async def test_read_missing_file_descriptive_error(workspace):
    obs = await dispatch("read_file", {"path": "nope.py"}, workspace)
    assert not obs.ok and obs.error


async def test_path_escape_rejected(workspace):
    obs = await dispatch("read_file", {"path": "../../etc/passwd"}, workspace)
    assert not obs.ok and "escapes workspace" in obs.error


async def test_absolute_path_outside_rejected(workspace, tmp_path_factory):
    outside = tmp_path_factory.mktemp("outside")
    (outside / "f.txt").write_text("x", encoding="utf-8")
    obs = await dispatch("read_file", {"path": str(outside / "f.txt")}, workspace)
    assert not obs.ok and "escapes workspace" in obs.error


async def test_symlink_escape_rejected(workspace, tmp_path_factory):
    outside = tmp_path_factory.mktemp("outside2")
    (outside / "secret.txt").write_text("secret", encoding="utf-8")
    link = workspace / "link.txt"
    try:
        os.symlink(outside / "secret.txt", link)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation not permitted on this host")
    obs = await dispatch("read_file", {"path": "link.txt"}, workspace)
    assert not obs.ok and "escapes workspace" in obs.error


async def test_read_truncates_large_file(workspace):
    (workspace / "big.txt").write_text("x" * 50_000, encoding="utf-8")
    obs = await dispatch("read_file", {"path": "big.txt"}, workspace)
    assert obs.ok and len(obs.content) < 50_000 and "truncated" in obs.content


async def test_list_files_skips_git_and_sorts(workspace):
    obs = await dispatch("list_files", {"path": "."}, workspace)
    assert obs.ok
    assert "README.md" in obs.content and "src/app.py" in obs.content
    assert ".git" not in obs.content


async def test_list_files_recursive_flag(workspace):
    flat = await dispatch("list_files", {"path": ".", "recursive": False}, workspace)
    assert "src/app.py" not in flat.content
    deep = await dispatch("list_files", {"path": ".", "recursive": True}, workspace)
    assert "src/app.py" in deep.content


async def test_search_code_finds_matches(workspace):
    obs = await dispatch("search_code", {"pattern": r"def add"}, workspace)
    assert obs.ok and "src/app.py:1" in obs.content


async def test_search_code_invalid_regex_error(workspace):
    obs = await dispatch("search_code", {"pattern": "("}, workspace)
    assert not obs.ok and "regex" in obs.error.lower()


async def test_search_code_respects_max_results(workspace):
    for i in range(10):
        (workspace / f"f{i}.py").write_text("needle\n", encoding="utf-8")
    obs = await dispatch("search_code", {"pattern": "needle", "max_results": 3}, workspace)
    assert obs.ok and obs.content.count("needle") <= 3