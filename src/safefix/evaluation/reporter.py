"""Report writers: machine-readable JSON, CSV summary, Markdown report."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from safefix.evaluation.metrics import RunRecord, SuiteSummary


def write_json(records: list[RunRecord], path: Path) -> None:
    Path(path).write_text(
        json.dumps([r.model_dump() for r in records], indent=2, ensure_ascii=False), encoding="utf-8"
    )


def write_csv(records: list[RunRecord], path: Path) -> None:
    fields = list(RunRecord.model_fields)
    with Path(path).open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for r in records:
            writer.writerow(r.model_dump())


def write_markdown(
    summary: SuiteSummary, records: list[RunRecord], path: Path, *, mode_note: str = ""
) -> None:
    lines = [
        "# SafeFix Evaluation Report",
        "",
        mode_note or "_Mode not specified — see results.json for run configuration._",
        "",
        "## Summary",
        "",
        f"- Runs: {summary.total_runs}",
        f"- Verified repairs: {summary.verified} ({summary.verified_rate:.0%})",
        f"- Reproduction success rate: {summary.repro_success_rate:.0%}",
        f"- Patch generation rate: {summary.patch_generation_rate:.0%}",
        f"- Average LLM calls: {summary.avg_llm_calls:.1f}",
        f"- Total tokens: {summary.total_tokens}",
        f"- Average duration: {summary.avg_duration_s:.1f}s",
        f"- Policy denials: {summary.policy_denials}",
        "",
        "## Failure categories",
        "",
    ]
    if summary.failure_categories:
        lines += [f"- {cat}: {count}" for cat, count in sorted(summary.failure_categories.items())]
    else:
        lines.append("- none")
    lines += [
        "",
        "## Runs",
        "",
        "| task | variant | status | halt | calls | tokens | category |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in records:
        lines.append(
            f"| {r.task_id} | {r.variant} | {r.status} | {r.halt_reason} | {r.llm_calls} | "
            f"{r.prompt_tokens + r.completion_tokens} | {r.failure_category or '-'} |"
        )
    lines += [
        "",
        "_Small sample: no statistical significance is claimed. See docs/evaluation.md for limitations._",
        "",
    ]
    Path(path).write_text("\n".join(lines), encoding="utf-8")
