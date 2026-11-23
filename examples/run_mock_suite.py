"""Deterministic MOCK pipeline validation over the full 5-task suite.

IMPORTANT: this uses a scripted provider (prewritten correct patches) to validate
the evaluation pipeline end-to-end. It is NOT evidence of live-model bug-fixing
capability and must never be reported as such. See docs/evaluation.md.

Run: uv run python examples/run_mock_suite.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests" / "unit"))

from local_executor import TrustedLocalExecutor  # noqa: E402  (test-only trusted executor)

from safefix.evaluation.runner import Variant, run_suite  # noqa: E402
from safefix.llm.mock import ScriptedMock  # noqa: E402
from safefix.security.approval import AutoApproveGateway  # noqa: E402

FIXES = {
    "paginate": (
        "--- a/shop/paginate.py\n+++ b/shop/paginate.py\n@@ -5,3 +5,3 @@\n"
        '     """Return the ``page``-th (1-based) slice of ``items`` with ``size`` per page."""\n'
        "-    start = page * size\n+    start = (page - 1) * size\n"
        "     return items[start : start + size]\n"
    ),
    "clamp": (
        "--- a/numtools/clamp.py\n+++ b/numtools/clamp.py\n@@ -2,8 +2,10 @@\n \n \n"
        " def clamp(value, lo, hi):\n+    if lo > hi:\n"
        '+        raise ValueError("lo must not exceed hi")\n'
        "     if value < lo:\n-        return hi\n+        return lo\n"
        "     if value > hi:\n         return hi\n     return value\n"
    ),
    "slugify": (
        "--- a/textutil/slugify.py\n+++ b/textutil/slugify.py\n@@ -7,3 +7,3 @@\n"
        "     text = text.lower().strip()\n"
        '     text = re.sub(r"[^a-z0-9]+", "-", text)\n'
        "-    return text\n+    return text.strip(\"-\")\n"
    ),
    "moving-average": (
        "--- a/statskit/average.py\n+++ b/statskit/average.py\n@@ -6,5 +6,5 @@\n"
        '         raise ValueError("window must be positive")\n'
        "     out = []\n"
        "-    for i in range(len(values) - window):\n"
        "+    for i in range(len(values) - window + 1):\n"
        "         out.append(sum(values[i : i + window]) / window)\n"
        "     return out\n"
    ),
    "binary-search": (
        "--- a/searchkit/bisect.py\n+++ b/searchkit/bisect.py\n@@ -10,3 +10,3 @@\n"
        "         else:\n             hi = mid\n"
        "-    return lo if lo < len(sorted_items) else -1\n"
        "+    return lo if lo < len(sorted_items) and sorted_items[lo] == target else -1\n"
    ),
}


def action(tool, args):
    return "```action\n" + json.dumps({"tool": tool, "args": args}) + "\n```"


def provider_for(spec, variant):
    diff = FIXES[spec["fixture"]]
    responses = [action("apply_patch", {"diff": diff}), action("finish", {})]
    if variant == Variant.A:
        responses = responses[:1]
    return ScriptedMock(responses)


async def main():
    root = Path(__file__).resolve().parents[1]
    out = root / "benchmarks" / "results" / "mock-pipeline-validation"
    records = await run_suite(
        root / "benchmarks" / "suite.yaml",
        provider_for=provider_for,
        executor=TrustedLocalExecutor(),
        approval=AutoApproveGateway(),
        out_dir=out,
        variants=(Variant.A, Variant.B, Variant.C),
        mode_note=(
            "**MOCK PIPELINE VALIDATION** — scripted provider with prewritten patches; "
            "trusted local test execution. NOT live-model benchmark performance."
        ),
    )
    verified = sum(r.status == "verified" for r in records)
    print(f"runs={len(records)} verified={verified} -> {out}")


if __name__ == "__main__":
    asyncio.run(main())