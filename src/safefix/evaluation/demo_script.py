"""Scripted fixer for explicit MOCK pipeline validation (never real-mode).

Contains known-correct patches for the shipped fixtures so the evaluation
pipeline can be exercised deterministically without a live model. Results produced
with this provider MUST be labelled as mock execution.
"""

from __future__ import annotations

import json

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
        '-    return text\n+    return text.strip("-")\n'
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


def _action(tool: str, args: dict) -> str:
    return "```action\n" + json.dumps({"tool": tool, "args": args}) + "\n```"


def mock_provider_for(spec: dict, variant):
    from safefix.evaluation.runner import Variant
    from safefix.llm.mock import ScriptedMock

    diff = FIXES[spec["fixture"]]
    responses = [_action("apply_patch", {"diff": diff}), _action("finish", {})]
    if variant == Variant.A:
        responses = responses[:1]
    return ScriptedMock(responses)
