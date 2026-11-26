"""Benchmark fixtures: small real Git repositories with genuine defects.

Each fixture directory contains:
- ``repo/``      the buggy project (implementation + agent-visible tests);
- ``eval/``      independent evaluation tests, NEVER copied into the agent workspace;
- ``task.yaml``  issue text, commands, budgets, license/defect metadata.

``materialize_fixture`` turns ``repo/`` into a real git repository with a base
commit, so the workflow exercises actual git history/diff machinery. The defects
are original fixtures reproducing common defect classes (off-by-one, validation,
edge cases) — they are not claimed to be CVEs from external projects.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[3]
# wheel force-include bundles data at the PACKAGE root (safefix/_fixtures, safefix/_suite.yaml)
_BUNDLED = Path(__file__).resolve().parent.parent / "_fixtures"


def fixtures_root() -> Path:
    """Dev checkout uses benchmarks/fixtures; installed wheels use bundled data."""
    dev = _REPO_ROOT / "benchmarks" / "fixtures"
    return dev if dev.is_dir() else _BUNDLED


def default_suite_path() -> Path:
    dev = _REPO_ROOT / "benchmarks" / "suite.yaml"
    if dev.is_file():
        return dev
    return Path(__file__).resolve().parent.parent / "_suite.yaml"


class FixtureError(Exception):
    pass


@dataclass
class Fixture:
    name: str
    repo_dir: Path
    eval_dir: Path
    meta: dict


def list_fixtures() -> list[str]:
    root = fixtures_root()
    if not root.is_dir():
        return []
    return sorted(p.name for p in root.iterdir() if (p / "task.yaml").is_file())


def load_fixture(name: str) -> Fixture:
    base = fixtures_root() / name
    if not (base / "task.yaml").is_file():
        raise FixtureError(f"unknown fixture: {name}")
    meta = yaml.safe_load((base / "task.yaml").read_text(encoding="utf-8"))
    repo_dir, eval_dir = base / "repo", base / "eval"
    if not repo_dir.is_dir() or not eval_dir.is_dir():
        raise FixtureError(f"fixture {name} missing repo/ or eval/")
    return Fixture(name=name, repo_dir=repo_dir, eval_dir=eval_dir, meta=meta)


def _git(cwd: Path, *args: str) -> None:
    proc = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=120)
    if proc.returncode != 0:
        raise FixtureError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")


def materialize_fixture(name: str, dest: Path) -> Path:
    """Copy the fixture project into ``dest`` and initialize a real git repo."""
    fx = load_fixture(name)
    dest = Path(dest)
    if dest.exists():
        raise FixtureError(f"destination already exists: {dest}")
    shutil.copytree(fx.repo_dir, dest)
    _git(dest, "init", "-q")
    _git(dest, "config", "user.email", "safefix@local")
    _git(dest, "config", "user.name", "SafeFix Fixture")
    _git(dest, "add", ".")
    _git(dest, "commit", "-qm", f"fixture base: {fx.meta['id']}")
    return dest
