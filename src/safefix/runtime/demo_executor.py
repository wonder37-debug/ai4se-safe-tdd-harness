"""Deterministic demo execution backend — runs NO processes, touches NO network.

For ``safefix demo`` only: it simulates pytest outcomes by inspecting the
workspace source (fixed marker present -> pass, otherwise realistic failure
output). Clearly labelled simulation; never used for real tasks, and never a
fallback for an unavailable sandbox.
"""

from __future__ import annotations

from pathlib import Path

from safefix.runtime.executor import ExecResult

_FAIL_OUTPUT = """F                                                                        [100%]
=================================== FAILURES ===================================
________________________________ test_first_page ________________________________

    def test_first_page():
>       assert paginate([1, 2, 3, 4, 5], 1, 2) == [1, 2]
E       assert [3, 4] == [1, 2]

tests/test_paginate.py:5: AssertionError
=========================== short test summary info ============================
FAILED tests/test_paginate.py::test_first_page - assert [3, 4] == [1, 2]
1 failed, 1 passed in 0.02s
"""

_PASS_OUTPUT = (
    "..                                                                       [100%]\n2 passed in 0.01s\n"
)


class DemoExecutor:
    """Simulated pytest for the paginate demo fixture (content-driven, deterministic)."""

    async def run(self, command: str, *, cwd: Path, timeout: float) -> ExecResult:
        impl = cwd / "shop" / "paginate.py"
        fixed = impl.exists() and "(page - 1) * size" in impl.read_text(encoding="utf-8")
        if fixed:
            return ExecResult(stdout=_PASS_OUTPUT, exit_code=0)
        return ExecResult(stdout=_FAIL_OUTPUT, exit_code=1)
