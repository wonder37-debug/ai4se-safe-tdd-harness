"""Optional Streamlit viewer for a recorded SafeFix run (localhost only).

Launch via: safefix ui --run-dir .safefix-runs/demo
Requires the optional UI extra: uv sync --extra ui

Displays task outcome, verification checks, tool timeline, test evidence, the
git diff and token usage. Never displays API keys or host files outside the
recorded run directory.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import streamlit as st


def main() -> None:
    run_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".safefix-runs/demo")
    st.set_page_config(page_title="SafeFix Run Viewer", layout="wide")
    st.title("SafeFix — run viewer")
    st.caption(f"run directory: {run_dir}")

    outcome_file = run_dir / "outcome.json"
    if not outcome_file.exists():
        st.error("No outcome.json found in this run directory.")
        return
    data = json.loads(outcome_file.read_text(encoding="utf-8"))

    col1, col2, col3 = st.columns(3)
    col1.metric("Status", data["status"])
    col2.metric("Halt reason", data["halt_reason"])
    col3.metric("LLM calls", data.get("llm_calls", 0))
    usage = data.get("usage", {})
    st.caption(
        f"tokens: {usage.get('prompt_tokens', 0)} in / {usage.get('completion_tokens', 0)} out · "
        f"duration: {data.get('duration_s', 0):.1f}s · base commit: {data.get('base_commit', '')[:12]}"
    )

    st.subheader("Independent verification")
    for c in data.get("verification", {}).get("checks", []):
        st.write(f"{'✅' if c['passed'] else '❌'} **{c['name']}** — {c['detail'][:200]}")
    if data.get("failure_analysis"):
        st.warning(data["failure_analysis"])

    st.subheader("Git diff (candidate patch)")
    st.code(data.get("patch", "") or "(empty)", language="diff")

    events_file = run_dir / "events.jsonl"
    if events_file.exists():
        st.subheader("Execution timeline")
        for line in events_file.read_text(encoding="utf-8").splitlines():
            ev = json.loads(line)
            payload = ev.get("payload", {})
            label = ev["type"]
            if label == "action":
                st.write(f"#{ev['seq']} 🔧 {payload.get('tool')} `{str(payload.get('args'))[:120]}`")
            elif label == "thought":
                st.write(f"#{ev['seq']} 💭 {payload.get('text', '')[:200]}")
            elif label == "approval_decision":
                st.write(f"#{ev['seq']} 🛡️ approval: {payload.get('decision')} ({payload.get('reason', '')})")
            elif label == "halt":
                st.write(f"#{ev['seq']} 🏁 halt: {payload.get('reason')}")


main()
