"""Execution backend contract.

Model-generated commands must NEVER run unrestricted on the host. The enforceable
backend is Docker (``docker_executor.py``); when it is unavailable the system must
fail with an explicit error rather than silently executing on the host.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from pydantic import BaseModel


class ExecResult(BaseModel):
    stdout: str = ""
    stderr: str = ""
    exit_code: int
    timed_out: bool = False
    duration_s: float = 0.0


class ExecutionBackend(Protocol):
    async def run(self, command: str, *, cwd: Path, timeout: float) -> ExecResult: ...


class SandboxUnavailableError(Exception):
    """Docker (or the configured sandbox) is not usable; untrusted execution refused."""