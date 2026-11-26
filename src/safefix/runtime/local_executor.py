"""Trusted local executor — explicit MOCK pipeline mode only.

Runs human-authored fixture commands (from task.yaml, never model-generated) on
the host for deterministic offline pipeline validation. Real-mode untrusted
execution ALWAYS goes through the Docker sandbox; this backend is never a
fallback for an unavailable sandbox.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

from safefix.runtime.executor import ExecResult
from safefix.runtime.output import bounded_communicate

_OUTPUT_CAP = 1_000_000


class LocalTrustedExecutor:
    async def run(self, command: str, *, cwd: Path, timeout: float) -> ExecResult:
        start = time.monotonic()
        proc = await asyncio.create_subprocess_shell(
            command,
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        out, err, timed_out = await bounded_communicate(proc, _OUTPUT_CAP, timeout)
        if timed_out:
            proc.kill()
            await proc.wait()
            return ExecResult(exit_code=-1, timed_out=True)
        return ExecResult(
            stdout=out,
            stderr=err,
            exit_code=proc.returncode or 0,
            duration_s=time.monotonic() - start,
        )
