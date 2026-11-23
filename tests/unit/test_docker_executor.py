"""Docker sandbox executor: hardened argv, refusal when unavailable, timeouts.

Live Docker integration lives in tests/integration (marked, skipped when the
daemon is down). These unit tests inject a fake spawn/check so the security
contract is verified offline and deterministically.
"""

import pytest

from safefix.runtime.docker_executor import DockerExecutor, SandboxLimits
from safefix.runtime.executor import ExecResult, SandboxUnavailableError


class FakeSpawn:
    def __init__(self, result: ExecResult):
        self.result = result
        self.calls: list[dict] = []

    async def __call__(self, argv, timeout):
        self.calls.append({"argv": argv, "timeout": timeout})
        return self.result


def make_executor(result=None, available=True):
    spawn = FakeSpawn(result or ExecResult(exit_code=0, stdout="ok"))
    ex = DockerExecutor(spawn=spawn, check_available=lambda: available)
    return ex, spawn


async def test_unavailable_docker_refuses_execution(tmp_path):
    ex, spawn = make_executor(available=False)
    with pytest.raises(SandboxUnavailableError, match="host"):
        await ex.run("pytest", cwd=tmp_path, timeout=10)
    assert spawn.calls == []  # never fell back to host execution


async def test_hardened_argv(tmp_path):
    ex, spawn = make_executor()
    await ex.run("python -m pytest -q", cwd=tmp_path, timeout=30)
    argv = spawn.calls[0]["argv"]
    joined = " ".join(argv)
    assert argv[0] == "docker" and argv[1] == "run"
    assert "--rm" in argv
    assert "--network" in argv and argv[argv.index("--network") + 1] == "none"
    assert "--user" in argv and argv[argv.index("--user") + 1] == "1000:1000"
    assert "--cap-drop" in argv and argv[argv.index("--cap-drop") + 1] == "ALL"
    assert "--security-opt" in argv and "no-new-privileges" in argv
    assert "--memory" in argv and "--cpus" in argv and "--pids-limit" in argv
    assert "--privileged" not in argv
    assert "docker.sock" not in joined
    assert f"src={tmp_path}" in joined and "dst=/work" in joined
    assert argv[-3:] == ["sh", "-c", "python -m pytest -q"]


async def test_no_host_environment_leakage(tmp_path, monkeypatch):
    monkeypatch.setenv("API_KEY", "sk-host-secret")
    ex, spawn = make_executor()
    await ex.run("pytest", cwd=tmp_path, timeout=10)
    argv = spawn.calls[0]["argv"]
    assert "--env" not in argv and "-e" not in argv
    assert "sk-host-secret" not in " ".join(argv)


async def test_timeout_maps_to_timed_out(tmp_path):
    ex, _ = make_executor(result=ExecResult(exit_code=-1, timed_out=True))
    result = await ex.run("pytest", cwd=tmp_path, timeout=1)
    assert result.timed_out


async def test_custom_limits(tmp_path):
    ex, spawn = make_executor()
    ex.limits = SandboxLimits(memory="1g", cpus="2.0", pids_limit=512, image="python:3.13-slim")
    await ex.run("pytest", cwd=tmp_path, timeout=10)
    argv = spawn.calls[0]["argv"]
    assert argv[argv.index("--memory") + 1] == "1g"
    assert argv[argv.index("--cpus") + 1] == "2.0"
    assert argv[argv.index("--pids-limit") + 1] == "512"
    assert "python:3.13-slim" in argv


def test_default_image_has_pytest_preinstalled():
    # python:3.12-slim lacks pytest; real runs need the prepared sandbox image
    # (root Dockerfile). Regression for 'No module named pytest' in real mode.
    assert SandboxLimits().image == "safefix-sandbox:latest"


async def test_container_user_matches_workspace_owner(tmp_path, monkeypatch):
    # Linux CI: workspace owned by uid 1001; fixed uid 1000 cannot write the bind
    # mount. Match the owner (still non-root). Windows reports uid 0 -> default.
    class FakeStat:
        st_uid = 1234
        st_gid = 1234

    monkeypatch.setattr(type(tmp_path), "stat", lambda self, **kw: FakeStat())
    ex, spawn = make_executor()
    await ex.run("pytest", cwd=tmp_path, timeout=10)
    argv = spawn.calls[0]["argv"]
    assert argv[argv.index("--user") + 1] == "1234:1234"


async def test_container_user_never_root(tmp_path, monkeypatch):
    class FakeStat:
        st_uid = 0
        st_gid = 0

    monkeypatch.setattr(type(tmp_path), "stat", lambda self, **kw: FakeStat())
    ex, spawn = make_executor()
    await ex.run("pytest", cwd=tmp_path, timeout=10)
    argv = spawn.calls[0]["argv"]
    assert argv[argv.index("--user") + 1] == "1000:1000"


async def test_trusted_prep_stage_has_network(tmp_path):
    ex, spawn = make_executor()
    await ex.run_trusted_prep("pip install -r requirements.txt", cwd=tmp_path, timeout=120)
    argv = spawn.calls[0]["argv"]
    assert argv[argv.index("--network") + 1] == "bridge"
