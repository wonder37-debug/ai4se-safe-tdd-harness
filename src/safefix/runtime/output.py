"""Bounded streaming reads for subprocess output.

``proc.communicate()`` buffers ALL output in host memory before any truncation,
so a chatty command can exhaust host RAM (container --memory does not constrain
the host Python process). These helpers drain the pipes continuously and retain
only the last ``cap`` bytes per stream (test summaries print last).
"""

from __future__ import annotations

import asyncio

_CHUNK = 65536
_TRUNC_MARKER = "\n...[output truncated]"


async def _drain(stream, cap: int) -> tuple[bytes, int]:
    buf = bytearray()
    total = 0
    while True:
        chunk = await stream.read(_CHUNK)
        if not chunk:
            break
        total += len(chunk)
        buf.extend(chunk)
        if len(buf) > cap:
            del buf[: len(buf) - cap]  # keep the tail, discard the rest
    return bytes(buf), total


async def bounded_communicate(proc, cap: int, timeout: float) -> tuple[str, str, bool]:
    """Return (stdout, stderr, timed_out) with bounded memory.

    On timeout the streams are abandoned; the CALLER must kill the process
    (and, for Docker, force-remove the container).
    """
    try:
        (out, out_total), (err, err_total) = await asyncio.wait_for(
            asyncio.gather(_drain(proc.stdout, cap), _drain(proc.stderr, cap)), timeout
        )
    except TimeoutError:
        return "", "", True
    await proc.wait()
    stdout = out.decode("utf-8", "replace") + (_TRUNC_MARKER if out_total > cap else "")
    stderr = err.decode("utf-8", "replace") + (_TRUNC_MARKER if err_total > cap else "")
    return stdout, stderr, False
