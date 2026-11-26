"""Fenced action protocol — Python port of legacy ``src/protocol/actionProtocol.ts``.

The LLM emits exactly one fenced block per turn::

    ```action
    {"tool": "read_file", "args": {"path": "src/app.py"}}
    ```

Behaviour preserved from the TypeScript original:
- unclosed fences are tolerated (models occasionally drop the closing backticks);
- malformed JSON blocks are skipped, never raised;
- unknown tool names and non-object ``args`` are rejected;
- ``strip_action_fences`` extracts the natural-language "thought" for event logging.
"""

from __future__ import annotations

import json
import re

from safefix.models import Action

# ``.*?`` + re.DOTALL == JS ``[\s\S]*?``; ``(?:```|$)`` tolerates an unclosed fence.
_FENCE = re.compile(r"```action\s*(.*?)(?:```|$)", re.DOTALL)

TOOL_NAMES: frozenset[str] = frozenset(
    {
        "list_files",
        "search_code",
        "read_file",
        "apply_patch",
        "run_tests",
        "git_status",
        "git_diff",
        "finish",
    }
)


def parse_actions(text: str) -> list[Action]:
    """Parse all valid action blocks in order; invalid blocks are silently skipped."""
    out: list[Action] = []
    for m in _FENCE.finditer(text):
        raw = m.group(1).strip()
        try:
            obj = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            continue
        if (
            isinstance(obj, dict)
            and isinstance(obj.get("tool"), str)
            and isinstance(obj.get("args"), dict)
            and obj["tool"] in TOOL_NAMES
        ):
            out.append(Action(tool=obj["tool"], args=obj["args"]))
    return out


def strip_action_fences(text: str) -> str:
    """Remove fenced action blocks, keeping only the natural-language thought text."""
    return _FENCE.sub("", text).strip()
