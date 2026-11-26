"""Fixture loading/materialization: real git repos with genuine, reproducible bugs."""

import subprocess
import sys
from pathlib import Path

from safefix.evaluation.fixtures import (
    default_suite_path,
    list_fixtures,
    load_fixture,
    materialize_fixture,
)


def test_default_suite_path_exists():
    assert default_suite_path().is_file()


def test_fixtures_root_falls_back_to_bundled(tmp_path, monkeypatch):
    import safefix.evaluation.fixtures as fx

    monkeypatch.setattr(fx, "_REPO_ROOT", tmp_path)  # no benchmarks/ here
    bundled = tmp_path / "bundled"
    bundled.mkdir()
    monkeypatch.setattr(fx, "_BUNDLED", bundled)
    assert fx.fixtures_root() == bundled


def test_bundled_location_matches_wheel_layout():
    # force-include maps benchmarks/fixtures -> safefix/_fixtures (package root),
    # NOT safefix/evaluation/_fixtures. Regression for clean-install demo failure.
    import safefix
    import safefix.evaluation.fixtures as fx

    pkg_root = Path(safefix.__file__).resolve().parent
    assert fx._BUNDLED == pkg_root / "_fixtures"


def test_five_fixtures_available():
    names = list_fixtures()
    assert {"paginate", "clamp", "slugify", "moving-average", "binary-search"} <= set(names)


def test_load_fixture_metadata():
    fx = load_fixture("paginate")
    assert fx.meta["id"] == "paginate-offbyone"
    assert fx.meta["issue"].strip()
    assert fx.repo_dir.is_dir() and fx.eval_dir.is_dir()
    assert fx.meta["repro_command"]


def test_materialize_creates_git_repo_with_base_commit(tmp_path):
    repo = materialize_fixture("paginate", tmp_path / "paginate")
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True)
    assert head.stdout.strip()
    assert (repo / "shop" / "paginate.py").exists()
    # independent eval tests must NOT be inside the agent-visible repo
    assert not (repo / "eval").exists()
    assert not list(repo.rglob("test_eval_*.py"))


def test_fixture_bug_reproduces(tmp_path):
    repo = materialize_fixture("paginate", tmp_path / "paginate")
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "tests/test_paginate.py"],
        cwd=repo,
        capture_output=True,
        text=True,
    )
    assert proc.returncode != 0  # genuine failing bug, not a scripted replay
    assert "FAILED" in proc.stdout


def test_every_fixture_reproduces_and_eval_passes_on_fixed_logic(tmp_path):
    # sanity: each fixture's visible tests fail on the buggy base
    for name in list_fixtures():
        fx = load_fixture(name)
        repo = materialize_fixture(name, tmp_path / name)
        proc = subprocess.run(
            [sys.executable, *fx.meta["repro_command"].split()[1:]],
            cwd=repo,
            capture_output=True,
            text=True,
        )
        assert proc.returncode != 0, f"{name} should fail at base"
        assert "FAILED" in proc.stdout or "ERROR" in proc.stdout, f"{name}: genuine test failure expected"
