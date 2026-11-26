"""P1 regressions: bounded subprocess output (4662795527) and real container
termination on timeout/cancel (4662992887).
"""

import asyncio
import sys

from safefix.runtime.docker_executor import DockerExecutor
from safefix.runtime.executor import ExecResult
from safefix.runtime.output import bounded_communicate


async def test_bounded_reader_caps_retained_memory():
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        "import sys; sys.stdout.write('x' * 8_000_000); sys.stdout.flush()",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, err, timed_out = await bounded_communicate(proc, cap=100_000, timeout=30)
    assert not timed_out
    assert len(out) <= 100_000 + 50  # cap + truncation marker
    assert "truncated" in out
    assert out.removesuffix("\n...[output truncated]").endswith("x" * 100)  # tail retained


async def test_bounded_reader_timeout_flag():
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        "import time; time.sleep(30)",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, _, timed_out = await bounded_communicate(proc, cap=1000, timeout=0.3)
    assert timed_out
    proc.kill()
    await proc.wait()


class CidFakeSpawn:
    """Writes the --cidfile like real docker, returns a configurable result."""

    def __init__(self, result: ExecResult, delay: float = 0.0):
        self.result = result
        self.delay = delay
        self.argv = None

    async def __call__(self, argv, timeout):
        self.argv = argv
        cid = argv[argv.index("--cidfile") + 1]
        from pathlib import Path

        Path(cid).write_text("fake-cid-123", encoding="utf-8")  # docker writes cid at container start
        if self.delay:
            await asyncio.sleep(self.delay)
        return self.result


async def test_timeout_force_removes_container(tmp_path):
    removed = []

    async def remover(cid):
        removed.append(cid)

    spawn = CidFakeSpawn(ExecResult(exit_code=-1, timed_out=True))
    ex = DockerExecutor(spawn=spawn, check_available=lambda: True, remove_container=remover)
    result = await ex.run("sleep 999", cwd=tmp_path, timeout=0.1)
    assert result.timed_out
    assert removed == ["fake-cid-123"], "container must be force-removed on timeout"
    assert "--cidfile" in spawn.argv


async def test_cancel_force_removes_container(tmp_path):
    removed = []

    async def remover(cid):
        removed.append(cid)

    spawn = CidFakeSpawn(ExecResult(exit_code=0), delay=5.0)
    ex = DockerExecutor(spawn=spawn, check_available=lambda: True, remove_container=remover)
    task = asyncio.create_task(ex.run("sleep 999", cwd=tmp_path, timeout=30))
    await asyncio.sleep(0.1)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    assert removed == ["fake-cid-123"], "container must be force-removed on cancel"


async def test_success_does_not_remove_and_cleans_cidfile(tmp_path):
    removed = []

    async def remover(cid):
        removed.append(cid)

    spawn = CidFakeSpawn(ExecResult(exit_code=0, stdout="ok"))
    ex = DockerExecutor(spawn=spawn, check_available=lambda: True, remove_container=remover)
    result = await ex.run("pytest", cwd=tmp_path, timeout=10)
    assert result.exit_code == 0 and removed == []
    cid_path = spawn.argv[spawn.argv.index("--cidfile") + 1]
    from pathlib import Path

    assert not Path(cid_path).exists(), "cidfile temp must be cleaned up"
