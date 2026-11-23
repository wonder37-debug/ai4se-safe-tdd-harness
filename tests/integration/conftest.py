"""Shared integration fixtures: ensure the prepared sandbox image exists."""

import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
IMAGE = "safefix-sandbox:latest"


def _docker_available() -> bool:
    try:
        subprocess.run(["docker", "info"], capture_output=True, timeout=20, check=True)
        return True
    except (OSError, subprocess.SubprocessError):
        return False


@pytest.fixture(scope="session", autouse=True)
def sandbox_image():
    """Build the sandbox image (root Dockerfile) if missing; skip when no Docker."""
    if not _docker_available():
        yield
        return
    inspect = subprocess.run(["docker", "image", "inspect", IMAGE], capture_output=True)
    if inspect.returncode != 0:
        subprocess.run(
            ["docker", "build", "-t", IMAGE, str(REPO_ROOT)],
            check=True,
            capture_output=True,
            timeout=600,
        )
    yield