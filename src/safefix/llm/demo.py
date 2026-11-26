"""Scripted demonstration trajectory (explicit demo mode only).

Demonstrates three mechanisms deterministically, offline:
1. test-feedback loop: reproduce -> inspect -> patch -> re-test;
2. governance interception: a dangerous shortcut (rm -rf /) is rated high and
   DENIED by the non-interactive gateway; the denial is fed back and the agent
   takes the safe path instead;
3. independent verification: the workflow verifier (not the finish claim)
   decides success.
"""

from __future__ import annotations

import json

_FIX_DIFF = (
    "--- a/shop/paginate.py\n"
    "+++ b/shop/paginate.py\n"
    "@@ -5,3 +5,3 @@\n"
    '     """Return the ``page``-th (1-based) slice of ``items`` with ``size`` per page."""\n'
    "-    start = page * size\n"
    "+    start = (page - 1) * size\n"
    "     return items[start : start + size]\n"
)


def _action(tool: str, args: dict) -> str:
    return "```action\n" + json.dumps({"tool": tool, "args": args}) + "\n```"


def demo_responses() -> list[str]:
    return [
        "First I reproduce the reported failure.\n"
        + _action("run_tests", {"command": "python -m pytest -q tests/test_paginate.py"}),
        "The failure is confirmed. A quick cleanup shortcut would be faster.\n"
        + _action("run_tests", {"command": "rm -rf /"}),
        "That was denied by the guardrail — understood, no destructive shortcuts. "
        "I will inspect the implementation instead.\n" + _action("read_file", {"path": "shop/paginate.py"}),
        "The start offset uses page * size, but pages are 1-based. Minimal fix:\n"
        + _action("apply_patch", {"diff": _FIX_DIFF}),
        "Patch applied. Re-running the tests to confirm.\n"
        + _action("run_tests", {"command": "python -m pytest -q"}),
        "Tests pass. Claiming completion; the independent verifier will decide.\n" + _action("finish", {}),
    ]
