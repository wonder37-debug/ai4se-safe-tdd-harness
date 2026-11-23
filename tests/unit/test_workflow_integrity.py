"""P1/P2 regressions: untracked files in patch+verification (4661696753),
test-config forgery (4662992875), fresh event log per run (4662795533),
fair single-shot context (4661696758), root-host writable workspace (4663355656).
"""

import json
import os
import subprocess
from pathlib import Path

import pytest
from local_executor import TrustedLocalExecutor

from safefix.agent.state import Budgets
from safefix.evaluation.fixtures import load_fixture, materialize_fixture
from safefix.llm.mock import ScriptedMock
from safefix.repair.workflow import RepairTask, run_repair
from safefix.runtime.workspace import prepare_workspace
from safefix.security.approval import AutoApproveGateway


def action(tool, args):
    return "```action\n" + json.dumps({"tool": tool, "args": args}) + "\n```"


def git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def make_repo(tmp_path, files: dict[str, str]):
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


NEW_FILE_DIFF = """--- /dev/null
+++ b/helper.py
@@ -0,0 +1,2 @@
+def fixed_value():
+    return 42
"""

IMPL_DIFF = """--- a/app.py
+++ b/app.py
@@ -1,2 +1,3 @@
-def value():
-    return 0
+from helper import fixed_value
+def value():
+    return fixed_value()
"""


async def test_new_file_included_in_patch_and_verification(tmp_path):
    repo = make_repo(
        tmp_path,
        {
            "app.py": "def value():\n    return 0\n",
            "tests/test_app.py": "from app import value\n\n\ndef test_value():\n    assert value() == 42\n",
        },
    )
    outcome = await run_repair(
        RepairTask(repo=str(repo), issue="value() must return 42"),
        provider=ScriptedMock(
            [
                action("apply_patch", {"diff": NEW_FILE_DIFF}),
                action("apply_patch", {"diff": IMPL_DIFF}),
                action("finish", {}),
            ]
        ),
        executor=TrustedLocalExecutor(),
        approval=AutoApproveGateway(),
        report_dir=tmp_path / "report",
    )
    assert outcome.status == "verified", outcome.failure_analysis
    assert "helper.py" in outcome.patch, "new file missing from exported patch"
    assert "fixed_value" in outcome.patch
    assert (tmp_path / "report" / "patch.diff").read_text(encoding="utf-8").count("helper.py") >= 1


async def test_pytest_ini_collect_only_forgery_rejected(tmp_path):
    repo = make_repo(
        tmp_path,
        {
            "app.py": "def value():\n    return 0\n",
            "pytest.ini": "[pytest]\n",
            "tests/test_app.py": "from app import value\n\n\ndef test_value():\n    assert value() == 42\n",
        },
    )
    forge = """--- a/pytest.ini
+++ b/pytest.ini
@@ -1 +1,2 @@
 [pytest]
+addopts = --collect-only
"""
    outcome = await run_repair(
        RepairTask(repo=str(repo), issue="value() must return 42"),
        provider=ScriptedMock([action("apply_patch", {"diff": forge}), action("finish", {})]),
        executor=TrustedLocalExecutor(),
        approval=AutoApproveGateway(),
        report_dir=tmp_path / "report",
    )
    assert outcome.status != "verified", "collect-only config forgery must not verify"
    names = {c.name: c.passed for c in outcome.verification.checks}
    assert not names.get("tests_untouched", True) or not names.get("repro_passes", True)


async def test_events_jsonl_fresh_per_run(tmp_path):
    source = materialize_fixture("paginate", tmp_path / "source")
    fx = load_fixture("paginate")
    report_dir = tmp_path / "report"
    fix = (
        "--- a/shop/paginate.py\n+++ b/shop/paginate.py\n@@ -5,3 +5,3 @@\n"
        '     """Return the ``page``-th (1-based) slice of ``items`` with ``size`` per page."""\n'
        "-    start = page * size\n+    start = (page - 1) * size\n"
        "     return items[start : start + size]\n"
    )
    for _ in range(2):
        await run_repair(
            RepairTask(repo=str(source), issue=fx.meta["issue"]),
            provider=ScriptedMock([action("apply_patch", {"diff": fix}), action("finish", {})]),
            executor=TrustedLocalExecutor(),
            approval=AutoApproveGateway(),
            report_dir=report_dir,
        )
    events = [
        json.loads(line) for line in (report_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    halts = [e for e in events if e["type"] == "halt"]
    assert len(halts) == 1, "old run events leaked into the new run"
    assert [e["seq"] for e in events] == list(range(1, len(events) + 1))


async def test_single_shot_preseed_context_enables_patch(tmp_path):
    source = materialize_fixture("paginate", tmp_path / "source")
    fx = load_fixture("paginate")
    fix = (
        "--- a/shop/paginate.py\n+++ b/shop/paginate.py\n@@ -5,3 +5,3 @@\n"
        '     """Return the ``page``-th (1-based) slice of ``items`` with ``size`` per page."""\n'
        "-    start = page * size\n+    start = (page - 1) * size\n"
        "     return items[start : start + size]\n"
    )
    outcome = await run_repair(
        RepairTask(
            repo=str(source),
            issue=fx.meta["issue"],
            budgets=Budgets(max_llm_calls=1, max_steps=1),
            preseed_context=True,
        ),
        provider=ScriptedMock([action("apply_patch", {"diff": fix})]),
        executor=TrustedLocalExecutor(),
        approval=AutoApproveGateway(),
        report_dir=tmp_path / "report",
    )
    assert outcome.status == "verified", outcome.failure_analysis
    assert outcome.llm_calls == 1


def test_workspace_exclude_and_root_chown(tmp_path, monkeypatch):
    repo = make_repo(tmp_path, {"app.py": "x = 1\n"})
    chowned = []
    monkeypatch.setattr(os, "geteuid", lambda: 0, raising=False)
    monkeypatch.setattr(
        os, "chown", lambda p, u, g, follow_symlinks=True: chowned.append((str(p), u, g)), raising=False
    )
    ws = prepare_workspace(str(repo), dest=tmp_path / "ws")
    exclude = (ws.path / ".git" / "info" / "exclude").read_text(encoding="utf-8")
    assert ".deps/" in exclude and ".safefix-memory/" in exclude and "_eval_verify/" in exclude
    assert chowned, "root host must transfer workspace ownership to sandbox uid"
    assert all(u == 1000 and g == 1000 for _, u, g in chowned)


def test_root_chown_does_not_follow_symlinks(tmp_path, monkeypatch):
    """Regression 4664964008: chown must not touch symlink TARGETS outside the clone."""
    outside = tmp_path / "outside"
    outside.mkdir()
    target = outside / "host-file"
    target.write_text("host data\n", encoding="utf-8")
    repo = make_repo(tmp_path, {"app.py": "x = 1\n"})
    try:
        os.symlink(target, repo / "link")
        subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-qm", "link"], cwd=repo, check=True, capture_output=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation not permitted on this host")
    chowned = []

    def spy_chown(p, u, g, follow_symlinks=True):
        chowned.append((str(p), u, g, follow_symlinks))

    monkeypatch.setattr(os, "geteuid", lambda: 0, raising=False)
    monkeypatch.setattr(os, "chown", spy_chown, raising=False)
    ws = prepare_workspace(str(repo), dest=tmp_path / "ws")
    assert chowned, "regular files must still be chowned"
    assert all(not follow for _, _, _, follow in chowned), "chown must not follow symlinks"
    assert not any(str(target) == p for p, _, _, _ in chowned), "external symlink target was chowned"
    assert not any((ws.path / "link").resolve() == Path(p) for p, _, _, _ in chowned)


async def test_type_change_of_test_file_rejected(tmp_path):
    """Regression 4664964020: file->symlink type change (T) on a test path is tampering."""
    from safefix.repair.verifier import verify_patch
    from safefix.runtime.executor import ExecResult

    repo = make_repo(
        tmp_path,
        {
            "app.py": "def value():\n    return 0\n",
            "helper.py": "def test_ok():\n    assert True\n",
            "tests/test_app.py": "from app import value\n\n\ndef test_value():\n    assert value() == 42\n",
        },
    )
    test_file = repo / "tests" / "test_app.py"
    test_file.unlink()
    try:
        os.symlink(repo / "helper.py", test_file)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation not permitted on this host")

    class PassingExecutor:
        async def run(self, command, *, cwd, timeout):
            return ExecResult(stdout="2 passed", exit_code=0)

    report = await verify_patch(
        repo,
        executor=PassingExecutor(),
        test_command="python -m pytest -q",
        repro_command=None,
        eval_dir=None,
    )
    assert not report.verified
    assert any(c.name == "tests_untouched" and not c.passed for c in report.checks)
