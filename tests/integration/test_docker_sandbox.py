"""Live Docker sandbox integration tests.

Skipped automatically when the Docker daemon is unreachable (never silently
executed on the host). Run with: uv run pytest tests/integration -m integration
"""

import subprocess

import pytest

from safefix.runtime.docker_executor import DockerExecutor
from safefix.runtime.executor import SandboxUnavailableError


def _docker_available() -> bool:
    try:
        subprocess.run(["docker", "info"], capture_output=True, timeout=20, check=True)
        return True
    except (OSError, subprocess.SubprocessError):
        return False


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not _docker_available(), reason="Docker daemon unavailable — sandbox integration NOT RUN"
    ),
]


@pytest.fixture(scope="module")
def executor():
    return DockerExecutor()


async def test_echo_runs_in_container(executor, tmp_path):
    result = await executor.run("echo hello-sandbox", cwd=tmp_path, timeout=300)
    assert result.exit_code == 0 and "hello-sandbox" in result.stdout


async def test_non_root_user(executor, tmp_path):
    result = await executor.run("id -u", cwd=tmp_path, timeout=120)
    assert result.exit_code == 0 and result.stdout.strip() == "1000"


async def test_network_disabled(executor, tmp_path):
    result = await executor.run(
        "python -c \"import socket; socket.create_connection(('example.com', 80), 3)\"",
        cwd=tmp_path,
        timeout=120,
    )
    assert result.exit_code != 0  # no network inside the sandbox


async def test_workspace_mount_writable(executor, tmp_path):
    result = await executor.run("echo data > /work/probe.txt", cwd=tmp_path, timeout=120)
    assert result.exit_code == 0
    assert (tmp_path / "probe.txt").read_text().strip() == "data"


async def test_host_env_not_leaked(executor, tmp_path, monkeypatch):
    monkeypatch.setenv("SAFEFIX_CANARY_SECRET", "do-not-leak")
    result = await executor.run("echo [$SAFEFIX_CANARY_SECRET]", cwd=tmp_path, timeout=120)
    assert result.exit_code == 0 and "do-not-leak" not in result.stdout


async def test_timeout_kills(executor, tmp_path):
    result = await executor.run("sleep 30", cwd=tmp_path, timeout=2)
    assert result.timed_out


async def test_unavailable_daemon_raises_explicit_error(tmp_path, monkeypatch):
    ex = DockerExecutor(check_available=lambda: False)
    with pytest.raises(SandboxUnavailableError):
        await ex.run("echo x", cwd=tmp_path, timeout=10)
