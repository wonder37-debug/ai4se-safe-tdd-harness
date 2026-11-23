"""Docker sandbox executor — the enforceable execution boundary.

Model-generated commands run ONLY inside a disposable container with:
non-root user, all capabilities dropped, no-new-privileges, no network,
CPU/memory/pids limits, wall-clock timeout, only the task workspace mounted,
no Docker socket, no host environment passed through, ``--rm`` cleanup.

If Docker is unavailable the executor raises ``SandboxUnavailableError`` —
it NEVER silently falls back to executing untrusted commands on the host.

Dependency installation is a separate, explicitly trusted preparation stage
(``run_trusted_prep``) with controlled network access; its commands come from
task configuration, not from the model.
"""

from __future__ import annotations

import asyncio
import inspect
import time
from collections.abc import Awaitable, Callable
from pathlib import Path

from pydantic import BaseModel, Field

from safefix.runtime.executor import ExecResult, SandboxUnavailableError

_OUTPUT_CAP = 1_000_000


class SandboxLimits(BaseModel):
    # Prepared sandbox image (root Dockerfile): python:3.12-slim + pytest + uid 1000.
    # Build once: docker build -t safefix-sandbox:latest .
    image: str = "safefix-sandbox:latest"
    memory: str = "512m"
    cpus: str = "1.0"
    pids_limit: int = Field(default=256, ge=1)
    user: str = "1000:1000"
    network: str = "none"
    workdir: str = "/work"


SpawnFn = Callable[[list[str], float], Awaitable[ExecResult]]


def _truncate(s: str) -> str:
    return s[:_OUTPUT_CAP] + "\n...[output truncated]" if len(s) > _OUTPUT_CAP else s


async def _default_spawn(argv: list[str], timeout: float) -> ExecResult:
    start = time.monotonic()
    proc = await asyncio.create_subprocess_exec(
        *argv,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return ExecResult(
            stdout=_truncate(out.decode("utf-8", "replace")),
            stderr=_truncate(err.decode("utf-8", "replace")),
            exit_code=proc.returncode or 0,
            duration_s=time.monotonic() - start,
        )
    except TimeoutError:
        proc.kill()
        await proc.wait()
        return ExecResult(exit_code=-1, timed_out=True, duration_s=time.monotonic() - start)


async def _default_check() -> bool:
    try:
        proc = await asyncio.create_subprocess_exec(
            "docker",
            "info",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await asyncio.wait_for(proc.communicate(), timeout=15)
        return proc.returncode == 0
    except (OSError, TimeoutError):
        return False


class DockerExecutor:
    def __init__(
        self,
        limits: SandboxLimits | None = None,
        *,
        spawn: SpawnFn | None = None,
        check_available: Callable[[], bool | Awaitable[bool]] | None = None,
    ):
        self.limits = limits or SandboxLimits()
        self._spawn = spawn or _default_spawn
        self._check = check_available or _default_check

    def _container_user(self, cwd: Path) -> str:
        """Match the workspace owner so the bind mount is writable, NEVER root.

        On Linux CI the workspace is owned by the runner uid (e.g. 1001); a fixed
        uid 1000 cannot write it. Windows stat reports uid 0 -> keep the default
        non-root user (Docker Desktop mounts are world-writable).
        """
        try:
            st = cwd.stat()
            uid, gid = st.st_uid, st.st_gid
        except OSError:
            return self.limits.user
        if uid == 0:
            return self.limits.user
        return f"{uid}:{gid}"

    def build_argv(self, command: str, cwd: Path, *, network: str | None = None) -> list[str]:
        lim = self.limits
        mount = f"type=bind,src={cwd},dst={lim.workdir}"
        return [
            "docker",
            "run",
            "--rm",
            "--network",
            network or lim.network,
            "--user",
            self._container_user(cwd),
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--memory",
            lim.memory,
            "--cpus",
            lim.cpus,
            "--pids-limit",
            str(lim.pids_limit),
            "--mount",
            mount,
            "-w",
            lim.workdir,
            lim.image,
            "sh",
            "-c",
            command,
        ]

    async def _available(self) -> bool:
        result = self._check()
        if inspect.isawaitable(result):
            result = await result
        return bool(result)

    async def run(self, command: str, *, cwd: Path, timeout: float) -> ExecResult:
        if not await self._available():
            raise SandboxUnavailableError(
                "Docker daemon is not reachable; refusing to execute untrusted commands on the host. "
                "Start Docker Desktop / the docker service, or run only deterministic mock tests."
            )
        return await self._spawn(self.build_argv(command, cwd), timeout)

    async def run_trusted_prep(self, command: str, *, cwd: Path, timeout: float) -> ExecResult:
        """Trusted preparation (e.g. pip install) with controlled network access.

        Commands here come from task configuration written by a human, never
        from the model. Still containerized with the same hardening.
        """
        if not await self._available():
            raise SandboxUnavailableError("Docker daemon is not reachable; trusted preparation refused.")
        return await self._spawn(self.build_argv(command, cwd, network="bridge"), timeout)
